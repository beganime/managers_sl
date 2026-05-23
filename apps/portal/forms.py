from django import forms

from apps.education.models import City, Country, Currency, Program, University
from apps.finance.models import Cashbox, Expense, ExpenseCategory, Income
from apps.projects_v2.models import Project, ProjectSection, ProjectTask


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


class PortalIncomeForm(PortalFormMixin, forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
    )

    class Meta:
        model = Income
        fields = [
            'cashbox',
            'title',
            'amount',
            'currency',
            'exchange_rate',
            'date',
            'source',
            'comment',
        ]
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, cashboxes=None, currencies=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cashbox'].queryset = cashboxes if cashboxes is not None else Cashbox.objects.all()
        self.fields['currency'].queryset = currencies if currencies is not None else Currency.objects.all()
        self.fields['currency'].required = False
        self.fields['source'].required = False
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
