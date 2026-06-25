from decimal import Decimal

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView

from apps.core.permissions import get_employee_profile
from apps.crm.models import Application, Client
from apps.erp_documents.models import (
    DocumentTemplate,
    GeneratedDocument,
    extract_docx_lines,
    find_stamp_rule,
    safe_document_title,
)
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
    if raw_value is None:
        return ''
    if isinstance(raw_value, Decimal):
        return str(raw_value)
    if hasattr(raw_value, 'isoformat'):
        return raw_value.isoformat()
    return raw_value


def widget_for_template_field(template_field):
    attrs = {'placeholder': template_field.help_text or template_field.label}
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
    template = forms.ModelChoiceField(label='Шаблон документа', queryset=DocumentTemplate.objects.none(), required=True)
    client = forms.ModelChoiceField(label='Клиент', queryset=Client.objects.none(), required=False)
    application = forms.ModelChoiceField(label='Заявка', queryset=Application.objects.none(), required=False)
    deal = forms.ModelChoiceField(label='Сделка', queryset=Deal.objects.none(), required=False)
    title = forms.CharField(label='Название документа', max_length=255, required=False)

    def __init__(
        self,
        *args,
        templates=None,
        clients=None,
        applications=None,
        deals=None,
        fixed_client=None,
        selected_client=None,
        selected_template=None,
        base_context=None,
        existing_document=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fixed_client = fixed_client
        self.selected_client = selected_client or fixed_client
        self.existing_document = existing_document
        self.base_context = base_context or {}
        self.template_field_names = []
        self.template_fields_map = {}

        self.fields['template'].queryset = templates if templates is not None else DocumentTemplate.objects.none()
        self.fields['client'].queryset = clients if clients is not None else Client.objects.none()
        self.fields['application'].queryset = applications if applications is not None else Application.objects.none()
        self.fields['deal'].queryset = deals if deals is not None else Deal.objects.none()

        # Клиент/заявка/сделка НЕ обязательны: можно создать общий документ только по шаблону.
        self.fields['client'].required = False
        self.fields['application'].required = False
        self.fields['deal'].required = False

        if fixed_client:
            self.fields['client'].queryset = Client.objects.filter(pk=fixed_client.pk)
            self.fields['client'].initial = fixed_client.pk
            self.fields['client'].widget = forms.HiddenInput()
        elif selected_client:
            self.fields['client'].initial = selected_client.pk

        if existing_document:
            self.fields['application'].initial = existing_document.application_id
            self.fields['deal'].initial = existing_document.deal_id
            self.fields['title'].initial = existing_document.title or ''

        template = self.resolve_selected_template(selected_template)
        if template:
            self.fields['template'].initial = template.pk
            self.add_template_fields(template)
            if not existing_document and self.selected_client and not self.data:
                self.fields['title'].initial = safe_document_title(template.name, self.selected_client.full_name)

        self.style_fields()

    def style_fields(self):
        for field in self.fields.values():
            css_class = 'select' if isinstance(field.widget, forms.Select) else 'input'
            if isinstance(field.widget, forms.Textarea):
                css_class = 'textarea'
            if isinstance(field.widget, (forms.CheckboxInput, forms.HiddenInput)):
                css_class = ''
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {css_class}'.strip()

    def resolve_selected_template(self, selected_template=None):
        if selected_template:
            return selected_template
        raw_value = self.data.get('template') if self.data else self.initial.get('template') if self.initial else None
        if not raw_value:
            return None
        try:
            return self.fields['template'].queryset.filter(pk=raw_value).prefetch_related('fields').first()
        except Exception:
            return None

    def initial_for_template_field(self, template_field):
        value = None
        if self.existing_document and isinstance(self.existing_document.context_data, dict):
            value = self.existing_document.context_data.get(template_field.key)
            if value in (None, '') and template_field.jinja_key:
                value = get_nested_value(self.existing_document.context_data, template_field.jinja_key)
        if value in (None, ''):
            value = self.base_context.get(template_field.key)
        if value in (None, '') and template_field.jinja_key:
            value = get_nested_value(self.base_context, template_field.jinja_key)
        if value in (None, '') and template_field.default_value:
            value = template_field.default_value
        return '' if value is None else value

    def add_template_fields(self, template):
        for template_field in template.fields.all().order_by('sort_order', 'label', 'key'):
            name = f'{FIELD_PREFIX}{template_field.pk}'
            label = template_field.label or template_field.jinja_key or template_field.key
            help_text = template_field.help_text or template_field.jinja_key or template_field.key
            widget = widget_for_template_field(template_field)

            if template_field.field_type == template_field.FIELD_TYPE_BOOLEAN:
                form_field = forms.BooleanField(label=label, required=False, help_text=help_text, widget=widget)
            elif template_field.field_type == template_field.FIELD_TYPE_DATE:
                form_field = forms.DateField(label=label, required=template_field.is_required, help_text=help_text, widget=widget, input_formats=['%Y-%m-%d'])
            elif template_field.field_type == template_field.FIELD_TYPE_NUMBER:
                form_field = forms.DecimalField(label=label, required=template_field.is_required, help_text=help_text, widget=widget)
            elif template_field.field_type == template_field.FIELD_TYPE_SELECT:
                form_field = forms.ChoiceField(label=label, required=template_field.is_required, help_text=help_text, widget=widget, choices=widget.choices)
            else:
                form_field = forms.CharField(label=label, required=template_field.is_required, help_text=help_text, widget=widget)

            form_field.initial = self.initial_for_template_field(template_field)
            self.fields[name] = form_field
            self.template_field_names.append(name)
            self.template_fields_map[name] = template_field

    def clean(self):
        # Нужен только шаблон. Клиент, заявка и сделка — опциональные привязки.
        return super().clean()

    def build_context_data(self):
        context_data = dict(self.existing_document.context_data or {}) if self.existing_document else {}
        for field_name, template_field in self.template_fields_map.items():
            value = normalize_dynamic_value(template_field, self.cleaned_data.get(field_name))
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


class DocumentReviewView(PortalContextMixin, TemplateView):
    template_name = 'portal/document_review.html'
    active_page = 'approvals'
    page_title = 'Проверка документа'

    def dispatch(self, request, *args, **kwargs):
        if not can_delete_admin(request.user):
            messages.error(request, 'Проверять документы может только администратор.')
            return redirect('portal:documents')
        return super().dispatch(request, *args, **kwargs)

    def get_document(self):
        return get_object_or_404(document_queryset(self.request.user), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_document()
        stamp_rule = find_stamp_rule(document)
        stamp_preview_options = document.stamp_preview_options or {}
        context.update({
            'document': document,
            'preview_lines': extract_docx_lines(document.generated_file) if document.generated_file else [],
            'stamp_rule': stamp_rule,
            'stamp_preview_options': stamp_preview_options,
            'default_stamp_mode': stamp_preview_options.get('stamp_mode') or 'executor',
            'default_stamp_width_mm': stamp_preview_options.get('stamp_width_mm') or (stamp_rule.width_mm if stamp_rule else 40),
            'default_stamp_height_mm': stamp_preview_options.get('stamp_height_mm') or (stamp_rule.height_mm if stamp_rule else 40),
            'default_stamp_x_percent': stamp_preview_options.get('stamp_x_percent') or 12,
            'default_stamp_y_percent': stamp_preview_options.get('stamp_y_percent') or 72,
            'default_page_number': stamp_preview_options.get('page_number') or '',
            'can_approve_with_stamp': document.template.allow_with_stamp,
            'can_download_original': document.can_download_original,
            'has_approved_pdf': bool(document.approved_file and str(document.approved_file.name).lower().endswith('.pdf')),
            'has_stamp_preview': document.has_stamp_preview,
            'stamp_preview_generated_at': document.stamp_preview_generated_at,
            'stamp_preview_generated_by': document.stamp_preview_generated_by,
        })
        return context


class DocumentCreateView(PortalContextMixin, TemplateView):
    template_name = 'portal/document_generate_form.html'
    active_page = 'documents'
    page_title = 'Создать документ'
    submit_label = 'Сгенерировать DOCX'
    success_url = reverse_lazy('portal:documents')

    def get_fixed_client(self):
        return None

    def get_document(self):
        return None

    def get_selected_template(self):
        document = self.get_document()
        if document:
            return document.template
        raw_template = self.request.POST.get('template') or self.request.GET.get('template')
        if not raw_template:
            return document_template_queryset(self.request.user).order_by('name').first()
        return document_template_queryset(self.request.user).filter(pk=raw_template).prefetch_related('fields').first()

    def get_selected_client(self):
        fixed_client = self.get_fixed_client()
        if fixed_client:
            return fixed_client
        document = self.get_document()
        if document and document.client_id:
            return document.client
        raw_client = self.request.POST.get('client') or self.request.GET.get('client')
        if not raw_client:
            return None
        return client_queryset(self.request.user).filter(pk=raw_client).first()

    def get_base_context_for_form(self, template=None, client=None):
        document = self.get_document()
        if document:
            return document.build_context()
        template = template or self.get_selected_template()
        client = client or self.get_selected_client()
        if not template:
            return {}
        employee = get_employee_profile(self.request.user)
        preview_document = GeneratedDocument(
            company=(client.company if client else (employee.company if employee else template.company)),
            office=(client.office if client and client.office_id else (employee.office if employee else None)),
            template=template,
            client=client,
            manager=(client.manager if client and client.manager_id else self.request.user),
        )
        return preview_document.build_context()

    def get_form(self, data=None):
        template = self.get_selected_template()
        client = self.get_selected_client()
        document = self.get_document()
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
            selected_client=client,
            selected_template=template,
            base_context=self.get_base_context_for_form(template=template, client=client),
            existing_document=document,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get('form') or self.get_form()
        client = self.get_selected_client()
        template = self.get_selected_template()
        document = self.get_document()
        context.update({
            'form': form,
            'client': client,
            'document': document,
            'is_regenerate': bool(document),
            'selected_client_id': client.pk if client else None,
            'selected_template': template,
            'selected_template_id': template.pk if template else None,
            'template_fields': form.template_fields_bound,
            'templates_count': document_template_queryset(self.request.user).count(),
            'clients_count': client_queryset(self.request.user).count(),
            'cancel_url': reverse_lazy('portal:documents'),
            'submit_label': self.submit_label,
        })
        return context

    def build_document(self, form):
        existing_document = self.get_document()
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
            company = (employee.company if employee else None) or template.company
            office = employee.office if employee else None
            manager = self.request.user

        if not company:
            raise ValueError('Не найдена компания для генерации документа. Укажите компанию в шаблоне или привяжите сотрудника к компании.')

        title = safe_document_title(
            template.name,
            client.full_name if client else '',
            form.cleaned_data.get('title') or '',
        )
        if existing_document:
            if existing_document.status == GeneratedDocument.STATUS_APPROVED:
                raise ValueError('Подтверждённый документ нельзя перегенерировать. Создайте новый документ.')
            existing_document.application = application
            existing_document.deal = deal
            existing_document.client = client
            existing_document.company = company
            existing_document.office = office
            existing_document.manager = manager
            existing_document.title = title
            existing_document.context_data = form.build_context_data()
            existing_document.status = GeneratedDocument.STATUS_DRAFT
            existing_document.generation_error = ''
            if existing_document.approved_file:
                existing_document.approved_file.delete(save=False)
                existing_document.approved_file = None
            existing_document.save(update_fields=[
                'application', 'deal', 'client', 'company', 'office', 'manager', 'title',
                'context_data', 'status', 'generation_error', 'approved_file', 'updated_at',
            ])
            return existing_document

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
                messages.success(request, 'Документ сгенерирован. DOCX доступен для скачивания в таблице документов.')
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
        context['selected_client_id'] = client.pk
        context['cancel_url'] = reverse('portal:client_detail', kwargs={'pk': client.pk})
        return context


class DocumentRegenerateView(DocumentCreateView):
    template_name = 'portal/document_generate_form.html'
    active_page = 'documents'
    page_title = 'Изменить и перегенерировать документ'
    submit_label = 'Перегенерировать DOCX'

    def get_document(self):
        return get_object_or_404(document_queryset(self.request.user), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.get_document()
        context['document'] = document
        context['client'] = document.client
        context['selected_client_id'] = document.client_id
        context['selected_template'] = document.template
        context['selected_template_id'] = document.template_id
        context['cancel_url'] = reverse('portal:documents')
        return context
