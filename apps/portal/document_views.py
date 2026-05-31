import json

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from apps.core.permissions import get_employee_profile
from apps.crm.models import Application, Client
from apps.erp_documents.models import DocumentTemplate, GeneratedDocument
from apps.finance.models import Deal

from .views import (
    ListPageMixin,
    PortalContextMixin,
    application_queryset,
    can_delete_admin,
    client_queryset,
    deal_queryset,
    document_queryset,
    document_template_queryset,
)


FIELD_PREFIX = 'tplfield__'


def get_nested_value(data, dotted_key):
    current = data
    for part in str(dotted_key or '').split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def set_nested_value(data, dotted_key, value):
    parts = [part for part in str(dotted_key or '').split('.') if part]
    if not parts:
        return
    current = data
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def normalize_dynamic_value(template_field, raw_value):
    if template_field.field_type == template_field.FIELD_TYPE_BOOLEAN:
        return bool(raw_value)
    return raw_value


def widget_for_template_field(template_field):
    attrs = {
        'placeholder': template_field.help_text or template_field.label,
    }
    if template_field.field_type == template_field.FIELD_TYPE_TEXTAREA:
        return forms.Textarea(attrs={**attrs, 'rows': 3})
    if template_field.field_type == template_field.FIELD_TYPE_DATE:
        return forms.DateInput(attrs={**attrs, 'type': 'date'})
    if template_field.field_type == template_field.FIELD_TYPE_NUMBER:
        return forms.NumberInput(attrs=attrs)
    if template_field.field_type == template_field.FIELD_TYPE_BOOLEAN:
        return forms.CheckboxInput(attrs={})
    if template_field.field_type == template_field.FIELD_TYPE_SELECT:
        choices = [('', '---------')]
        options = template_field.options or []
        for option in options:
            if isinstance(option, dict):
                value = option.get('value') or option.get('key') or option.get('label') or ''
                label = option.get('label') or value
            else:
                value = option
                label = option
            choices.append((value, label))
        return forms.Select(choices=choices, attrs=attrs)
    return forms.TextInput(attrs=attrs)


class PortalDocumentGenerateForm(forms.Form):
    template = forms.ModelChoiceField(
        label='Шаблон документа',
        queryset=DocumentTemplate.objects.none(),
        required=True,
    )
    client = forms.ModelChoiceField(
        label='Клиент',
        queryset=Client.objects.none(),
        required=False,
    )
    application = forms.ModelChoiceField(
        label='Заявка',
        queryset=Application.objects.none(),
        required=False,
    )
    deal = forms.ModelChoiceField(
        label='Сделка',
        queryset=Deal.objects.none(),
        required=False,
    )
    title = forms.CharField(
        label='Название документа',
        max_length=255,
        required=False,
    )

    def __init__(
        self,
        *args,
        templates=None,
        clients=None,
        applications=None,
        deals=None,
        fixed_client=None,
        selected_template=None,
        base_context=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fixed_client = fixed_client
        self.base_context = base_context or {}
        self.template_field_names = []
        self.template_fields_map = {}

        self.fields['template'].queryset = templates if templates is not None else DocumentTemplate.objects.none()
        self.fields['client'].queryset = clients if clients is not None else Client.objects.none()
        self.fields['application'].queryset = applications if applications is not None else Application.objects.none()
        self.fields['deal'].queryset = deals if deals is not None else Deal.objects.none()

        if fixed_client:
            self.fields['client'].queryset = Client.objects.filter(pk=fixed_client.pk)
            self.fields['client'].initial = fixed_client.pk
            self.fields['client'].required = False
            self.fields['client'].widget = forms.HiddenInput()
        else:
            self.fields['client'].required = True

        template = self.resolve_selected_template(selected_template)
        if template:
            self.fields['template'].initial = template.pk
            self.add_template_fields(template)

        self.style_fields()

    def style_fields(self):
        for field in self.fields.values():
            css_class = 'select' if isinstance(field.widget, forms.Select) else 'input'
            if isinstance(field.widget, forms.Textarea):
                css_class = 'textarea'
            if isinstance(field.widget, forms.CheckboxInput) or isinstance(field.widget, forms.HiddenInput):
                css_class = ''
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {css_class}'.strip()

    def resolve_selected_template(self, selected_template=None):
        if selected_template:
            return selected_template
        raw_value = None
        if self.data:
            raw_value = self.data.get('template')
        elif self.initial:
            raw_value = self.initial.get('template')
        if not raw_value:
            return None
        try:
            return self.fields['template'].queryset.filter(pk=raw_value).prefetch_related('fields').first()
        except Exception:
            return None

    def initial_for_template_field(self, template_field):
        value = self.base_context.get(template_field.key)
        if value in (None, '') and template_field.jinja_key:
            value = get_nested_value(self.base_context, template_field.jinja_key)
        if value in (None, '') and template_field.default_value:
            value = template_field.default_value
        return '' if value is None else value

    def add_template_fields(self, template):
        for template_field in template.fields.all().order_by('sort_order', 'label', 'key'):
            name = f'{FIELD_PREFIX}{template_field.pk}'
            form_field = forms.Field(
                label=template_field.label or template_field.jinja_key or template_field.key,
                required=template_field.is_required,
                help_text=template_field.help_text or template_field.jinja_key or template_field.key,
                widget=widget_for_template_field(template_field),
            )
            if template_field.field_type == template_field.FIELD_TYPE_BOOLEAN:
                form_field = forms.BooleanField(
                    label=template_field.label or template_field.jinja_key or template_field.key,
                    required=False,
                    help_text=template_field.help_text or template_field.jinja_key or template_field.key,
                    widget=widget_for_template_field(template_field),
                )
            elif template_field.field_type == template_field.FIELD_TYPE_DATE:
                form_field = forms.DateField(
                    label=template_field.label or template_field.jinja_key or template_field.key,
                    required=template_field.is_required,
                    help_text=template_field.help_text or template_field.jinja_key or template_field.key,
                    widget=widget_for_template_field(template_field),
                    input_formats=['%Y-%m-%d'],
                )
            elif template_field.field_type == template_field.FIELD_TYPE_NUMBER:
                form_field = forms.DecimalField(
                    label=template_field.label or template_field.jinja_key or template_field.key,
                    required=template_field.is_required,
                    help_text=template_field.help_text or template_field.jinja_key or template_field.key,
                    widget=widget_for_template_field(template_field),
                )
            elif template_field.field_type == template_field.FIELD_TYPE_SELECT:
                form_field = forms.ChoiceField(
                    label=template_field.label or template_field.jinja_key or template_field.key,
                    required=template_field.is_required,
                    help_text=template_field.help_text or template_field.jinja_key or template_field.key,
                    widget=widget_for_template_field(template_field),
                    choices=widget_for_template_field(template_field).choices,
                )

            form_field.initial = self.initial_for_template_field(template_field)
            self.fields[name] = form_field
            self.template_field_names.append(name)
            self.template_fields_map[name] = template_field

    def clean(self):
        cleaned_data = super().clean()
        client = self.fixed_client or cleaned_data.get('client')
        application = cleaned_data.get('application')
        deal = cleaned_data.get('deal')
        if not client and not application and not deal:
            raise forms.ValidationError('Выберите клиента, заявку или сделку для генерации документа.')
        return cleaned_data

    def build_context_data(self):
        context_data = {}
        for field_name, template_field in self.template_fields_map.items():
            value = self.cleaned_data.get(field_name)
            value = normalize_dynamic_value(template_field, value)
            if value in (None, '') and not template_field.is_required:
                continue
            if hasattr(value, 'isoformat'):
                value = value.isoformat()
            context_data[template_field.key] = value
            if template_field.jinja_key:
                if '.' in template_field.jinja_key:
                    set_nested_value(context_data, template_field.jinja_key, value)
                else:
                    context_data[template_field.jinja_key] = value
        return context_data

    @property
    def template_fields_bound(self):
        return [self[name] for name in self.template_field_names]


class DocumentsView(ListPageMixin):
    active_page = 'documents'
    page_title = 'Документы'
    table_template = 'portal/partials/documents_table.html'
    grid_template = 'portal/partials/documents_grid.html'
    search_fields = ('title', 'template__name', 'client__full_name', 'deal__title')
    status_choices = GeneratedDocument.STATUS_CHOICES
    create_url_name = 'portal:document_create'
    create_label = 'Создать документ'

    def get_queryset(self):
        return document_queryset(self.request.user)

    def get_extra_context(self, qs):
        return {
            'pending_documents': qs.filter(status=GeneratedDocument.STATUS_PENDING).count(),
            'can_review_documents': can_delete_admin(self.request.user),
            'templates_count': document_template_queryset(self.request.user).count(),
        }


class DocumentCreateView(PortalContextMixin, TemplateView):
    template_name = 'portal/document_generate_form.html'
    active_page = 'documents'
    page_title = 'Создать документ'
    success_url = reverse_lazy('portal:documents')

    def get_fixed_client(self):
        return None

    def get_selected_template(self):
        raw_template = self.request.POST.get('template') or self.request.GET.get('template')
        if not raw_template:
            return document_template_queryset(self.request.user).order_by('name').first()
        return document_template_queryset(self.request.user).filter(pk=raw_template).prefetch_related('fields').first()

    def get_selected_client(self):
        fixed_client = self.get_fixed_client()
        if fixed_client:
            return fixed_client
        raw_client = self.request.POST.get('client') or self.request.GET.get('client')
        if not raw_client:
            return None
        return client_queryset(self.request.user).filter(pk=raw_client).first()

    def get_base_context_for_form(self, template=None, client=None):
        template = template or self.get_selected_template()
        client = client or self.get_selected_client()
        if not template:
            return {}
        employee = get_employee_profile(self.request.user)
        preview_document = GeneratedDocument(
            company=(client.company if client else (employee.company if employee else None)),
            office=(client.office if client and client.office_id else (employee.office if employee else None)),
            template=template,
            client=client,
            manager=(client.manager if client and client.manager_id else self.request.user),
        )
        return preview_document.build_context()

    def get_form(self, data=None):
        template = self.get_selected_template()
        client = self.get_selected_client()
        applications = application_queryset(self.request.user)
        deals = deal_queryset(self.request.user)
        if client:
            applications = applications.filter(client=client)
            deals = deals.filter(client=client)
        return PortalDocumentGenerateForm(
            data=data,
            templates=document_template_queryset(self.request.user).order_by('name'),
            clients=client_queryset(self.request.user).order_by('-updated_at'),
            applications=applications.order_by('-created_at'),
            deals=deals.order_by('-created_at'),
            fixed_client=self.get_fixed_client(),
            selected_template=template,
            base_context=self.get_base_context_for_form(template=template, client=client),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get('form') or self.get_form()
        client = self.get_selected_client()
        template = self.get_selected_template()
        context.update({
            'form': form,
            'client': client,
            'selected_template': template,
            'template_fields': form.template_fields_bound,
            'templates_count': document_template_queryset(self.request.user).count(),
            'clients_count': client_queryset(self.request.user).count(),
            'cancel_url': reverse_lazy('portal:documents'),
        })
        return context

    def build_document(self, form):
        template = form.cleaned_data['template']
        client = self.get_fixed_client() or form.cleaned_data.get('client')
        application = form.cleaned_data.get('application')
        deal = form.cleaned_data.get('deal')
        employee = get_employee_profile(self.request.user)

        if deal:
            client = client or deal.client
            application = application or deal.application
            company = deal.company
            office = deal.office
            manager = deal.manager or self.request.user
        elif application:
            client = client or application.client
            company = application.company
            office = application.office
            manager = application.manager or self.request.user
        elif client:
            company = client.company
            office = client.office or (employee.office if employee else None)
            manager = client.manager or self.request.user
        else:
            company = employee.company if employee else template.company
            office = employee.office if employee else None
            manager = self.request.user

        if not company:
            raise ValueError('Не найдена компания для генерации документа.')

        title = form.cleaned_data.get('title') or f'{template.name} - {client.full_name if client else self.request.user}'
        return GeneratedDocument.objects.create(
            company=company,
            office=office,
            template=template,
            client=client,
            application=application,
            deal=deal,
            manager=manager,
            title=title,
            context_data=form.build_context_data(),
        )

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if form.is_valid():
            try:
                document = self.build_document(form)
                document.generate_file()
                messages.success(
                    request,
                    'Документ создан. Ссылка на скачивание DOCX доступна в таблице документов.',
                )
                return redirect('portal:documents')
            except Exception as exc:
                messages.error(request, f'Ошибка генерации документа: {exc}')
        context = self.get_context_data()
        context['form'] = form
        context['template_fields'] = form.template_fields_bound
        return self.render_to_response(context)


class ClientDocumentCreateView(DocumentCreateView):
    template_name = 'portal/document_generate_form.html'
    active_page = 'documents'
    page_title = 'Создать документ клиента'

    def get_fixed_client(self):
        return get_object_or_404(client_queryset(self.request.user), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_fixed_client()
        context['client'] = client
        context['cancel_url'] = reverse_lazy('portal:client_detail', kwargs={'pk': client.pk})
        return context
