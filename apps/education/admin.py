from django import forms
from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .models import City, Country, Currency, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact


def get_usd_currency():
    currency, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$', 'rate_to_usd': '1.000000'},
    )
    return currency


@admin.register(Country)
class CountryAdmin(ModelAdmin):
    list_display = ('name', 'code', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основное', {'fields': ('name', 'code', 'flag', 'description')}),
        ('Публикация', {'fields': ('sort_order', 'is_active')}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(City)
class CityAdmin(ModelAdmin):
    list_display = ('name', 'country', 'sort_order', 'is_active')
    list_filter = ('country', 'is_active')
    search_fields = ('name', 'country__name')
    autocomplete_fields = ('country',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основное', {'fields': ('country', 'name', 'description')}),
        ('Публикация', {'fields': ('sort_order', 'is_active')}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(Currency)
class CurrencyAdmin(ModelAdmin):
    list_display = ('code', 'name', 'symbol', 'rate_to_usd', 'updated_at')
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основное', {'fields': ('code', 'name', 'symbol', 'rate_to_usd')}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


class UniversityProgramInlineForm(forms.ModelForm):
    tuition_fee_usd = forms.DecimalField(
        label='Стоимость программы USD',
        required=False,
        max_digits=14,
        decimal_places=2,
        min_value=0,
        initial=0,
    )
    service_fee_usd = forms.DecimalField(
        label='Стоимость услуг USD',
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
    )

    class Meta:
        model = Program
        fields = (
            'name',
            'degree',
            'faculty',
            'language',
            'duration',
            'description',
            'is_active',
            'is_archived',
            'tuition_fee_usd',
            'service_fee_usd',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            fee = self.instance.fees.filter(currency__code='USD').order_by('-created_at', '-id').first()
            if not fee:
                fee = self.instance.fees.order_by('-created_at', '-id').first()
            if fee:
                self.fields['tuition_fee_usd'].initial = fee.tuition_fee
                self.fields['service_fee_usd'].initial = fee.service_fee_usd


class UniversityProgramInlineFormSet(BaseInlineFormSet):
    def save_new(self, form, commit=True):
        instance = super().save_new(form, commit=commit)
        if commit:
            self.save_program_fee(form, instance)
        return instance

    def save_existing(self, form, instance, commit=True):
        instance = super().save_existing(form, instance, commit=commit)
        if commit:
            self.save_program_fee(form, instance)
        return instance

    def save_program_fee(self, form, program):
        if not program.pk or not form.cleaned_data or form.cleaned_data.get('DELETE'):
            return
        tuition_fee = form.cleaned_data.get('tuition_fee_usd')
        service_fee = form.cleaned_data.get('service_fee_usd')
        if tuition_fee in (None, '') and service_fee in (None, ''):
            return
        currency = get_usd_currency()
        fee = program.fees.filter(currency=currency).order_by('-created_at', '-id').first()
        if not fee:
            fee = ProgramFee(program=program, currency=currency)
        fee.tuition_fee = tuition_fee or 0
        fee.service_fee_usd = service_fee or 0
        fee.save()


class ProgramInline(TabularInline):
    model = Program
    form = UniversityProgramInlineForm
    formset = UniversityProgramInlineFormSet
    extra = 1
    fields = (
        'name',
        'degree',
        'faculty',
        'language',
        'duration',
        'tuition_fee_usd',
        'service_fee_usd',
        'description',
        'is_active',
        'is_archived',
    )
    show_change_link = True


class UniversityRequiredDocumentInline(TabularInline):
    model = RequiredDocument
    extra = 1
    fields = ('program', 'title', 'description', 'is_mandatory', 'sort_order', 'is_active')
    autocomplete_fields = ('program',)
    show_change_link = True


class UniversityContactInline(TabularInline):
    model = UniversityContact
    extra = 1
    fields = ('full_name', 'position', 'email', 'phone', 'messenger', 'notes', 'is_active')
    show_change_link = True


class ProgramFeeInlineForm(forms.ModelForm):
    class Meta:
        model = ProgramFee
        fields = (
            'currency',
            'tuition_fee',
            'service_fee_usd',
            'application_fee',
            'dormitory_fee',
            'insurance_fee',
            'notes',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['currency'].initial = get_usd_currency()


class ProgramFeeInline(TabularInline):
    model = ProgramFee
    form = ProgramFeeInlineForm
    extra = 1
    fields = (
        'currency',
        'tuition_fee',
        'service_fee_usd',
        'application_fee',
        'dormitory_fee',
        'insurance_fee',
        'notes',
    )
    autocomplete_fields = ('currency',)
    show_change_link = True


class IntakeInline(TabularInline):
    model = Intake
    extra = 1
    fields = ('title', 'start_date', 'application_deadline', 'notes', 'is_active')
    show_change_link = True


class ProgramRequiredDocumentInline(TabularInline):
    model = RequiredDocument
    fk_name = 'program'
    extra = 1
    fields = ('title', 'description', 'is_mandatory', 'sort_order', 'is_active')
    show_change_link = True


@admin.register(University)
class UniversityAdmin(ModelAdmin):
    list_display = ('name', 'country', 'city', 'website', 'is_active', 'updated_at')
    list_filter = ('is_active', 'country', 'city')
    search_fields = ('name', 'legal_name', 'country__name', 'city__name', 'website', 'email')
    autocomplete_fields = ('company', 'country', 'city', 'local_currency', 'added_by')
    readonly_fields = ('logo_preview', 'cover_preview', 'program_fee_hint', 'created_at', 'updated_at')
    inlines = [ProgramInline, UniversityRequiredDocumentInline, UniversityContactInline]
    fieldsets = (
        ('Основное', {
            'fields': ('company', 'name', 'legal_name', 'country', 'city', 'local_currency', 'is_active'),
            'description': 'Если страны, города или валюты ещё нет, добавьте её через плюс рядом с полем или через раздел «ВУЗы и программы».',
        }),
        ('Контакты', {'fields': ('website', 'email', 'phone', 'address')}),
        ('Описание для клиентов', {
            'fields': (
                'description',
                'admission_requirements',
                'invitation_info',
                'dormitory_info',
                'expenses_info',
                'age_limit',
            )
        }),
        ('Изображения', {'fields': ('logo', 'logo_preview', 'cover_image', 'cover_preview')}),
        ('Следующий шаг', {'fields': ('program_fee_hint',)}),
        ('Внутреннее', {'fields': ('commission_info', 'custom_data', 'added_by'), 'classes': ('collapse',)}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Логотип')
    def logo_preview(self, obj):
        if obj and obj.logo:
            return format_html(
                '<img src="{}" style="max-width:140px; max-height:100px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />',
                obj.logo.url,
            )
        return 'Логотип не загружен'

    @admin.display(description='Обложка')
    def cover_preview(self, obj):
        if obj and obj.cover_image:
            return format_html(
                '<img src="{}" style="max-width:220px; max-height:120px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />',
                obj.cover_image.url,
            )
        return 'Обложка не загружена'

    @admin.display(description='Стоимость программ')
    def program_fee_hint(self, obj):
        if not obj or not obj.pk:
            return 'Сначала сохраните ВУЗ. После сохранения ниже можно добавить программы, затем открыть программу и сразу заполнить стоимость, наборы и документы.'
        url = reverse('admin:education_program_changelist')
        return format_html(
            '<div style="line-height:1.5">'
            'Программы добавляются в inline-блоке ниже. Чтобы добавить стоимость, наборы/intakes и документы на одной странице, '
            'откройте нужную программу по ссылке «Изменить» в inline-блоке или через раздел '
            '<a href="{}?university__id__exact={}">Программы</a>. '
            'Если добавили ВУЗ, обязательно добавьте хотя бы одну программу.'
            '</div>',
            url,
            obj.pk,
        )


@admin.register(Program)
class ProgramAdmin(ModelAdmin):
    list_display = ('name', 'university', 'degree', 'language', 'duration', 'is_active', 'is_archived')
    list_filter = ('degree', 'language', 'is_active', 'is_archived', 'university__country')
    search_fields = ('name', 'faculty', 'university__name', 'university__country__name')
    autocomplete_fields = ('university',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ProgramFeeInline, IntakeInline, ProgramRequiredDocumentInline]
    fieldsets = (
        ('Основное', {'fields': ('university', 'name', 'degree', 'faculty', 'language', 'duration')}),
        ('Описание и требования', {'fields': ('description', 'admission_requirements')}),
        ('Публикация', {'fields': ('is_active', 'is_archived')}),
        ('Расширенные данные', {'fields': ('custom_data',), 'classes': ('collapse',)}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(Intake)
class IntakeAdmin(ModelAdmin):
    list_display = ('title', 'program', 'start_date', 'application_deadline', 'is_active')
    list_filter = ('is_active', 'start_date', 'application_deadline')
    search_fields = ('title', 'program__name', 'program__university__name')
    autocomplete_fields = ('program',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основное', {'fields': ('program', 'title', 'start_date', 'application_deadline', 'notes')}),
        ('Публикация', {'fields': ('is_active',)}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(RequiredDocument)
class RequiredDocumentAdmin(ModelAdmin):
    list_display = ('title', 'university', 'program', 'is_mandatory', 'sort_order', 'is_active')
    list_filter = ('is_mandatory', 'is_active')
    search_fields = ('title', 'university__name', 'program__name')
    autocomplete_fields = ('university', 'program')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Привязка', {'fields': ('university', 'program')}),
        ('Документ', {'fields': ('title', 'description', 'is_mandatory')}),
        ('Публикация', {'fields': ('sort_order', 'is_active')}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(UniversityContact)
class UniversityContactAdmin(ModelAdmin):
    list_display = ('university', 'full_name', 'position', 'email', 'phone', 'is_active')
    list_filter = ('is_active', 'university__country')
    search_fields = ('university__name', 'full_name', 'position', 'email', 'phone')
    autocomplete_fields = ('university',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('ВУЗ', {'fields': ('university',)}),
        ('Контакт', {'fields': ('full_name', 'position', 'email', 'phone', 'messenger', 'notes')}),
        ('Публикация', {'fields': ('is_active',)}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
