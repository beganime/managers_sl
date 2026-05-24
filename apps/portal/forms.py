from django import forms

from apps.crm.models import Application, Client, Lead, LeadSource
from apps.education.models import City, Country, Currency, Program, University
from apps.erp_documents.models import DocumentTemplate, GeneratedDocument
from apps.erp_services.models import Service, ServiceCategory
from apps.finance.models import Cashbox, Deal, Expense, ExpenseCategory, Income, Payment
from apps.knowledge.models import KnowledgeArticle, KnowledgeAttachment, KnowledgeCategory
from apps.portal.models import CalendarEvent
from apps.projects_v2.models import (
    Project,
    ProjectSection,
    ProjectTask,
    TaskAttachment,
    TaskChecklist,
    TaskChecklistItem,
    TaskComment,
)


class PortalFormMixin:
    """Apply portal UI classes to Django widgets."""

    def style_fields(self):
        for field in self.fields.values():
            css_class = 'select' if isinstance(field.widget, forms.Select) else 'input'
            if isinstance(field.widget, forms.Textarea):
                css_class = 'textarea'
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = ''
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {css_class}'.strip()


class PortalUniversityForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = University
        fields = [
            'country',
            'city',
            'local_currency',
            'name',
            'legal_name',
            'website',
            'email',
            'phone',
            'address',
            'description',
            'admission_requirements',
            'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'admission_requirements': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, countries=None, cities=None, currencies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['country'].queryset = countries if countries is not None else Country.objects.all()
        self.fields['city'].queryset = cities if cities is not None else City.objects.all()
        self.fields['local_currency'].queryset = currencies if currencies is not None else Currency.objects.all()
        self.fields['city'].required = False
        self.fields['local_currency'].required = False
        self.fields['legal_name'].required = False
        self.fields['website'].required = False
        self.fields['email'].required = False
        self.fields['phone'].required = False
        self.fields['address'].required = False
        self.style_fields()


class PortalProgramForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = Program
        fields = [
            'university',
            'name',
            'degree',
            'faculty',
            'language',
            'duration',
            'description',
            'admission_requirements',
            'is_active',
            'is_archived',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'admission_requirements': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, universities=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['university'].queryset = universities if universities is not None else University.objects.all()
        self.fields['faculty'].required = False
        self.fields['language'].required = False
        self.fields['duration'].required = False
        self.style_fields()


class PortalTaskForm(PortalFormMixin, forms.ModelForm):
    deadline = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )

    class Meta:
        model = ProjectTask
        fields = [
            'project',
            'section',
            'title',
            'description',
            'assigned_to',
            'priority',
            'status',
            'deadline',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, projects=None, sections=None, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = projects if projects is not None else Project.objects.all()
        self.fields['section'].queryset = sections if sections is not None else ProjectSection.objects.all()
        self.fields['assigned_to'].queryset = employees if employees is not None else self.fields['assigned_to'].queryset
        self.fields['section'].required = False
        self.fields['assigned_to'].required = False
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        project = cleaned_data.get('project')
        section = cleaned_data.get('section')
        if project and section and section.project_id != project.id:
            self.add_error('section', 'Section must belong to the selected project.')
        return cleaned_data


class PortalProjectForm(PortalFormMixin, forms.ModelForm):
    deadline = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )

    class Meta:
        model = Project
        fields = [
            'title',
            'code',
            'description',
            'status',
            'deadline',
            'owner',
            'participants',
            'responsible_users',
            'is_pinned',
            'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'participants': forms.SelectMultiple(attrs={'size': 6}),
            'responsible_users': forms.SelectMultiple(attrs={'size': 6}),
        }

    def __init__(self, *args, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        users = employees if employees is not None else self.fields['owner'].queryset
        self.fields['owner'].queryset = users
        self.fields['participants'].queryset = users
        self.fields['responsible_users'].queryset = users
        self.fields['code'].required = False
        self.fields['owner'].required = False
        self.style_fields()


class PortalProjectSectionForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectSection
        fields = ['title', 'description', 'color', 'sort_order', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['color'].required = False
        self.style_fields()


class PortalTaskCommentForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['text']
        widgets = {'text': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Комментарий к задаче'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class PortalTaskChecklistForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = TaskChecklist
        fields = ['title']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class PortalTaskChecklistItemForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = TaskChecklistItem
        fields = ['title', 'is_done']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.style_fields()


class PortalTaskAttachmentForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = TaskAttachment
        fields = ['title', 'attachment_type', 'file', 'url', 'note']
        widgets = {'note': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False
        self.fields['file'].required = False
        self.fields['url'].required = False
        self.fields['note'].required = False
        self.style_fields()


class PortalClientForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'full_name',
            'phone',
            'email',
            'direction',
            'status',
            'manager',
            'office',
            'lead_source',
            'comments',
            'dob',
            'citizenship',
            'city',
            'address',
            'address_registration',
            'passport_local_num',
            'passport_inter_num',
            'passport_issued_by',
            'passport_issued_date',
            'passport_valid_until',
            'passport_birth_place',
            'relative_full_name',
            'relative_relation',
            'relative_phone',
            'relative_workplace',
            'current_education',
            'current_school',
            'current_study_country',
            'interested_country',
            'interested_university',
            'interested_program',
            'has_passport',
            'has_education_doc',
            'has_translation',
            'has_photo',
        ]
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            'passport_issued_date': forms.DateInput(attrs={'type': 'date'}),
            'passport_valid_until': forms.DateInput(attrs={'type': 'date'}),
            'comments': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, managers=None, offices=None, sources=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['manager'].queryset = managers if managers is not None else self.fields['manager'].queryset
        self.fields['office'].queryset = offices if offices is not None else self.fields['office'].queryset
        self.fields['lead_source'].queryset = sources if sources is not None else LeadSource.objects.all()
        self.fields['phone'].required = False
        self.fields['email'].required = False
        self.fields['direction'].required = False
        self.fields['manager'].required = False
        self.fields['office'].required = False
        self.fields['lead_source'].required = False
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        phone = (cleaned_data.get('phone') or '').strip()
        email = (cleaned_data.get('email') or '').strip()
        direction = (cleaned_data.get('direction') or '').strip()
        interested_country = (cleaned_data.get('interested_country') or '').strip()
        interested_program = (cleaned_data.get('interested_program') or '').strip()
        if not phone and not email:
            raise forms.ValidationError('Укажите телефон или email клиента.')
        if not direction and not interested_country and not interested_program:
            raise forms.ValidationError('Укажите направление или интерес клиента.')
        return cleaned_data


class PortalServiceForm(PortalFormMixin, forms.ModelForm):
    category_name = forms.CharField(required=False, max_length=150)

    class Meta:
        model = Service
        fields = [
            'category',
            'category_name',
            'title',
            'code',
            'description',
            'price_client',
            'real_cost',
            'currency',
            'is_active',
            'is_public',
        ]
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, categories=None, currencies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = categories if categories is not None else ServiceCategory.objects.all()
        self.fields['currency'].queryset = currencies if currencies is not None else Currency.objects.all()
        self.fields['category'].required = False
        self.fields['code'].required = False
        self.fields['currency'].required = False
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('category') and not cleaned_data.get('category_name'):
            self.add_error('category_name', 'Выберите категорию или напишите новую.')
        return cleaned_data


class PortalDealForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            'client',
            'application',
            'deal_type',
            'service',
            'title',
            'university_name',
            'program_name',
            'currency',
            'price_client',
            'comment',
        ]
        widgets = {'comment': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, clients=None, applications=None, services=None, currencies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = clients if clients is not None else Client.objects.all()
        self.fields['application'].queryset = applications if applications is not None else Application.objects.all()
        self.fields['service'].queryset = services if services is not None else Service.objects.all()
        self.fields['currency'].queryset = currencies if currencies is not None else Currency.objects.all()
        self.fields['application'].required = False
        self.fields['service'].required = False
        self.fields['university_name'].required = False
        self.fields['program_name'].required = False
        self.fields['title'].required = False
        self.fields['currency'].required = False
        self.fields['price_client'].required = False
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        service = cleaned_data.get('service')
        title = (cleaned_data.get('title') or '').strip()
        if not service and not title:
            self.add_error('title', 'Выберите услугу или напишите название вручную.')
        if not cleaned_data.get('currency') and not (service and service.currency_id):
            self.add_error('currency', 'Выберите валюту.')
        return cleaned_data


class PortalPaymentForm(PortalFormMixin, forms.ModelForm):
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
    )

    class Meta:
        model = Payment
        fields = ['deal', 'cashbox', 'amount', 'currency', 'exchange_rate', 'method', 'payment_date', 'comment']
        widgets = {'comment': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, deals=None, cashboxes=None, currencies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deal'].queryset = deals if deals is not None else Deal.objects.all()
        self.fields['cashbox'].queryset = cashboxes if cashboxes is not None else Cashbox.objects.all()
        self.fields['currency'].queryset = currencies if currencies is not None else Currency.objects.all()
        self.fields['cashbox'].required = False
        self.style_fields()


class PortalDocumentGenerateForm(PortalFormMixin, forms.Form):
    template = forms.ModelChoiceField(queryset=DocumentTemplate.objects.none())
    application = forms.ModelChoiceField(queryset=Application.objects.none(), required=False)
    deal = forms.ModelChoiceField(queryset=Deal.objects.none(), required=False)
    title = forms.CharField(max_length=255, required=False)
    context_data = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4}))

    def __init__(self, *args, templates=None, applications=None, deals=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['template'].queryset = templates if templates is not None else DocumentTemplate.objects.none()
        self.fields['application'].queryset = applications if applications is not None else Application.objects.none()
        self.fields['deal'].queryset = deals if deals is not None else Deal.objects.none()
        self.style_fields()


class PortalKnowledgeCategoryForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = KnowledgeCategory
        fields = ['parent', 'name', 'code', 'description', 'icon', 'color', 'is_public', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, categories=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = categories if categories is not None else KnowledgeCategory.objects.all()
        self.fields['parent'].required = False
        self.fields['code'].required = False
        self.fields['icon'].required = False
        self.fields['color'].required = False
        self.style_fields()


class PortalKnowledgeArticleForm(PortalFormMixin, forms.ModelForm):
    attachment_title = forms.CharField(required=False, max_length=255)
    attachment_file = forms.FileField(required=False)
    attachment_url = forms.URLField(required=False)

    class Meta:
        model = KnowledgeArticle
        fields = ['category', 'title', 'slug', 'summary', 'content', 'status', 'is_featured', 'is_public', 'is_active']
        widgets = {
            'summary': forms.Textarea(attrs={'rows': 3}),
            'content': forms.Textarea(attrs={'rows': 12}),
        }

    def __init__(self, *args, categories=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = categories if categories is not None else KnowledgeCategory.objects.all()
        self.fields['category'].required = False
        self.fields['slug'].required = False
        self.style_fields()

    def save_attachment(self, article, user):
        title = self.cleaned_data.get('attachment_title') or ''
        file = self.cleaned_data.get('attachment_file')
        url = self.cleaned_data.get('attachment_url') or ''
        if not file and not url:
            return None
        attachment_type = KnowledgeAttachment.TYPE_LINK if url and not file else KnowledgeAttachment.TYPE_FILE
        return KnowledgeAttachment.objects.create(
            article=article,
            uploaded_by=user,
            title=title,
            attachment_type=attachment_type,
            file=file,
            url=url,
        )


class PortalCalendarEventForm(PortalFormMixin, forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = ['office', 'participants', 'title', 'description', 'event_date', 'start_time', 'end_time', 'visibility']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'event_date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'participants': forms.SelectMultiple(attrs={'size': 5}),
        }

    def __init__(self, *args, offices=None, users=None, is_admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['office'].queryset = offices
        self.fields['participants'].queryset = users
        self.fields['office'].required = False
        self.fields['participants'].required = False
        self.fields['start_time'].required = False
        self.fields['end_time'].required = False
        self.fields['description'].required = False
        if not is_admin:
            self.fields['visibility'].choices = [
                choice for choice in CalendarEvent.VISIBILITY_CHOICES
                if choice[0] != CalendarEvent.VISIBILITY_COMPANY
            ]
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        if start_time and end_time and end_time < start_time:
            self.add_error('end_time', 'End time must be later than start time.')
        return cleaned_data


class PortalIncomeForm(PortalFormMixin, forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
    )

    class Meta:
        model = Income
        fields = [
            'cashbox',
            'client',
            'deal',
            'service',
            'title',
            'amount',
            'currency',
            'exchange_rate',
            'date',
            'source',
            'proof_file',
            'comment',
        ]
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, cashboxes=None, clients=None, deals=None, services=None, currencies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cashbox'].queryset = cashboxes if cashboxes is not None else Cashbox.objects.all()
        self.fields['client'].queryset = clients if clients is not None else Client.objects.all()
        self.fields['deal'].queryset = deals if deals is not None else Deal.objects.all()
        self.fields['service'].queryset = services if services is not None else Service.objects.all()
        self.fields['currency'].queryset = currencies if currencies is not None else Currency.objects.all()
        self.fields['client'].required = False
        self.fields['deal'].required = False
        self.fields['service'].required = False
        self.fields['currency'].required = False
        self.fields['source'].required = False
        self.fields['proof_file'].required = False
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('currency') and not cleaned_data.get('cashbox'):
            self.add_error('currency', 'Choose a currency or cashbox.')
        return cleaned_data


class PortalExpenseForm(PortalFormMixin, forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
    )
    confirm_now = forms.BooleanField(required=False)

    class Meta:
        model = Expense
        fields = [
            'category',
            'cashbox',
            'title',
            'amount',
            'currency',
            'exchange_rate',
            'date',
            'comment',
        ]
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, categories=None, cashboxes=None, currencies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = categories if categories is not None else ExpenseCategory.objects.all()
        self.fields['cashbox'].queryset = cashboxes if cashboxes is not None else Cashbox.objects.all()
        self.fields['currency'].queryset = currencies if currencies is not None else Currency.objects.all()
        self.fields['cashbox'].required = False
        self.fields['currency'].required = False
        self.style_fields()

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('currency') and not cleaned_data.get('cashbox'):
            self.add_error('currency', 'Choose a currency or cashbox.')
        return cleaned_data
