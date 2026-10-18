from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.forms.models import BaseInlineFormSet
from django.template.response import TemplateResponse
from django.urls import path
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .forms import ProgramJsonImportForm
from .importers import import_programs_from_json
from .models import City, Country, Currency, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact


def get_usd_currency():
    currency, _ = Currency.objects.get_or_create(
        code='USD',
        defaults={'name': 'US Dollar', 'symbol': '$', 'rate_to_usd': '1.000000'},
    )
    return currency


@admin.register(Country)
class CountryAdmin(ModelAdmin):
    list_display = ('name', 'code', 'country_image_preview', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('flag_preview', 'country_image_preview', 'country_cover_preview', 'created_at', 'updated_at')
    fieldsets = (
        ('Основное', {'fields': ('name', 'code', 'flag', 'description')}),
        ('Публикация', {'fields': ('sort_order', 'is_active')}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_fieldsets(self, request, obj=None):
        return (
            ('Основное', {'fields': ('name', 'code', 'description')}),
            ('Изображения', {'fields': ('flag', 'flag_preview', 'image', 'country_image_preview', 'cover_image', 'country_cover_preview')}),
            ('Публикация', {'fields': ('sort_order', 'is_active')}),
            ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
        )

    def render_image_preview(self, file_field, empty_text):
        if file_field:
            return format_html(
                '<img src="{}" style="max-width:160px; max-height:100px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />',
                file_field.url,
            )
        return empty_text

    @admin.display(description='Флаг')
    def flag_preview(self, obj):
        return self.render_image_preview(obj.flag if obj else None, '-')

    @admin.display(description='Изображение')
    def country_image_preview(self, obj):
        return self.render_image_preview(obj.image if obj else None, '-')

    @admin.display(description='Обложка')
    def country_cover_preview(self, obj):
        return self.render_image_preview(obj.cover_image if obj else None, '-')


@admin.register(City)
class CityAdmin(ModelAdmin):
    list_display = ('name', 'country', 'city_image_preview', 'sort_order', 'is_active')
    list_filter = ('country', 'is_active')
    search_fields = ('name', 'country__name')
    autocomplete_fields = ('country',)
    readonly_fields = ('city_image_preview', 'city_cover_preview', 'created_at', 'updated_at')
    fieldsets = (
        ('Основное', {'fields': ('country', 'name', 'description')}),
        ('Публикация', {'fields': ('sort_order', 'is_active')}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_fieldsets(self, request, obj=None):
        return (
            ('Основное', {'fields': ('country', 'name', 'description')}),
            ('Изображения', {'fields': ('image', 'city_image_preview', 'cover_image', 'city_cover_preview')}),
            ('Публикация', {'fields': ('sort_order', 'is_active')}),
            ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
        )

    def render_image_preview(self, file_field, empty_text):
        if file_field:
            return format_html(
                '<img src="{}" style="max-width:160px; max-height:100px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />',
                file_field.url,
            )
        return empty_text

    @admin.display(description='Изображение')
    def city_image_preview(self, obj):
        return self.render_image_preview(obj.image if obj else None, '-')

    @admin.display(description='Обложка')
    def city_cover_preview(self, obj):
        return self.render_image_preview(obj.cover_image if obj else None, '-')


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
    application_fee_usd = forms.DecimalField(
        label='Application fee USD',
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
    )
    dormitory_fee_usd = forms.DecimalField(
        label='Общежитие USD',
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=0,
        initial=0,
    )
    insurance_fee_usd = forms.DecimalField(
        label='Страховка USD',
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
            'application_fee_usd',
            'dormitory_fee_usd',
            'insurance_fee_usd',
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
                self.fields['application_fee_usd'].initial = fee.application_fee
                self.fields['dormitory_fee_usd'].initial = fee.dormitory_fee
                self.fields['insurance_fee_usd'].initial = fee.insurance_fee


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
        application_fee = form.cleaned_data.get('application_fee_usd')
        dormitory_fee = form.cleaned_data.get('dormitory_fee_usd')
        insurance_fee = form.cleaned_data.get('insurance_fee_usd')
        fee_values = (tuition_fee, service_fee, application_fee, dormitory_fee, insurance_fee)
        if all(value in (None, '') for value in fee_values):
            return
        currency = get_usd_currency()
        fee = program.fees.filter(currency=currency).order_by('-created_at', '-id').first()
        if not fee:
            fee = ProgramFee(program=program, currency=currency)
        fee.tuition_fee = tuition_fee or 0
        fee.service_fee_usd = service_fee or 0
        fee.application_fee = application_fee or 0
        fee.dormitory_fee = dormitory_fee or 0
        fee.insurance_fee = insurance_fee or 0
        fee.save()


class ProgramInline(TabularInline):
    model = Program
    form = UniversityProgramInlineForm
    formset = UniversityProgramInlineFormSet
    extra = 0
    min_num = 0
    fields = (
        'name',
        'degree',
        'faculty',
        'language',
        'duration',
        'tuition_fee_usd',
        'service_fee_usd',
        'application_fee_usd',
        'dormitory_fee_usd',
        'insurance_fee_usd',
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
    list_display = ('name', 'abbreviation', 'country', 'city', 'website', 'is_active', 'updated_at')
    list_filter = ('is_active', 'country', 'city')
    search_fields = ('name', 'abbreviation', 'legal_name', 'country__name', 'city__name', 'website', 'email')
    autocomplete_fields = ('company', 'country', 'city', 'local_currency', 'added_by')
    readonly_fields = ('logo_preview', 'cover_preview', 'program_fee_hint', 'created_at', 'updated_at')
    inlines = [ProgramInline, UniversityRequiredDocumentInline, UniversityContactInline]
    fieldsets = (
        ('Основное', {
            'fields': ('company', 'name', 'abbreviation', 'legal_name', 'country', 'city', 'local_currency', 'is_active'),
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
            return 'Программы можно добавить сейчас или позже на странице ВУЗа. ВУЗ можно сохранить без программ.'
        url = reverse('admin:education_program_changelist')
        return format_html(
            '<div style="line-height:1.5">'
            'Программы можно добавить сейчас или позже на странице ВУЗа. '
            'Если программа уже известна, добавьте её в inline-блоке ниже и сразу заполните основные стоимости в USD: стоимость обучения, стоимость услуг, application fee, общежитие и страховка. '
            'Для intakes и документов конкретной программы откройте нужную программу по ссылке «Изменить» в inline-блоке или через раздел '
            '<a href="{}?university__id__exact={}">Программы</a>. '
            'Сохранение ВУЗа без программ разрешено.'
            '</div>',
            url,
            obj.pk,
        )


@admin.register(Program)
class ProgramAdmin(ModelAdmin):
    change_list_template = 'admin/education/program/change_list.html'
    list_display = (
        'name',
        'university',
        'country',
        'city',
        'degree',
        'language',
        'duration',
        'tuition_usd',
        'service_usd',
        'intakes_count',
        'documents_count',
        'is_active',
        'is_archived',
    )
    list_filter = ('degree', 'language', 'is_active', 'is_archived', 'university__country', 'university__city')
    search_fields = ('name', 'faculty', 'university__name', 'university__country__name', 'university__city__name')
    autocomplete_fields = ('university',)
    readonly_fields = ('university_overview', 'created_at', 'updated_at')
    list_select_related = ('university', 'university__country', 'university__city')
    list_per_page = 50
    actions = ('mark_active', 'mark_archived', 'mark_unarchived')
    inlines = [ProgramFeeInline, IntakeInline, ProgramRequiredDocumentInline]
    fieldsets = (
        ('Основное', {'fields': ('university', 'university_overview', 'name', 'degree', 'faculty', 'language', 'duration')}),
        ('Описание и требования', {'fields': ('description', 'admission_requirements')}),
        ('Публикация', {'fields': ('is_active', 'is_archived')}),
        ('Расширенные данные', {'fields': ('custom_data',), 'classes': ('collapse',)}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'import-json/',
                self.admin_site.admin_view(self.import_json_view),
                name='education_program_import_json',
            ),
        ]
        return custom_urls + urls

    def import_json_view(self, request):
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            raise PermissionDenied

        result = None
        if request.method == 'POST':
            form_data = request.POST.copy()
            run_mode = form_data.get('run_mode')
            if run_mode == 'dry_run':
                form_data['dry_run'] = 'on'
            elif run_mode == 'import':
                form_data.pop('dry_run', None)
            else:
                form_data['dry_run'] = 'on'

            form = ProgramJsonImportForm(form_data, request.FILES)
            if form.is_valid():
                result = import_programs_from_json(
                    form.cleaned_data['json_file'].read(),
                    dry_run=form.cleaned_data['dry_run'],
                    update_existing=form.cleaned_data['update_existing'],
                )
                if result.has_errors:
                    self.message_user(
                        request,
                        f'Импорт завершён с ошибками: {len(result.errors)}. Создано: {result.created}, обновлено: {result.updated}, пропущено: {result.skipped}.',
                        level=messages.WARNING,
                    )
                else:
                    mode = 'Тестовый импорт' if result.dry_run else 'Импорт'
                    self.message_user(
                        request,
                        f'{mode} завершён успешно. Создано: {result.created}, обновлено: {result.updated}, пропущено: {result.skipped}.',
                    )
        else:
            form = ProgramJsonImportForm()

        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': 'Импорт программ из JSON',
            'form': form,
            'result': result,
            'has_view_permission': self.has_view_permission(request),
        }
        return TemplateResponse(request, 'admin/education/program/import_json.html', context)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            admin_intakes_count=Count('intakes', distinct=True),
            admin_documents_count=Count('required_documents', distinct=True),
        )

    def latest_fee(self, obj):
        fee = obj.fees.select_related('currency').filter(currency__code='USD').order_by('-created_at', '-id').first()
        if fee:
            return fee
        return obj.fees.select_related('currency').order_by('-created_at', '-id').first()

    def format_money(self, value):
        if value in (None, ''):
            return '-'
        return f'${value:,.2f}'

    def convert_fee_to_usd(self, fee, value):
        if not fee or value in (None, ''):
            return None
        rate = getattr(fee.currency, 'rate_to_usd', None) or Decimal('1')
        return Decimal(value) * Decimal(rate)

    @admin.display(description='Страна', ordering='university__country__name')
    def country(self, obj):
        return obj.university.country.name if obj.university_id and obj.university.country_id else '-'

    @admin.display(description='Город', ordering='university__city__name')
    def city(self, obj):
        return obj.university.city.name if obj.university_id and obj.university.city_id else '-'

    @admin.display(description='Обучение USD')
    def tuition_usd(self, obj):
        fee = self.latest_fee(obj)
        return self.format_money(self.convert_fee_to_usd(fee, fee.tuition_fee if fee else None))

    @admin.display(description='Услуги USD')
    def service_usd(self, obj):
        fee = self.latest_fee(obj)
        return self.format_money(fee.service_fee_usd if fee else None)

    @admin.display(description='Наборы', ordering='admin_intakes_count')
    def intakes_count(self, obj):
        return getattr(obj, 'admin_intakes_count', 0)

    @admin.display(description='Документы', ordering='admin_documents_count')
    def documents_count(self, obj):
        return getattr(obj, 'admin_documents_count', 0)

    @admin.display(description='ВУЗ / локация')
    def university_overview(self, obj):
        if not obj or not obj.university_id:
            return 'Выберите ВУЗ, затем сохраните программу.'
        university = obj.university
        location = ', '.join(part for part in (
            university.country.name if university.country_id else '',
            university.city.name if university.city_id else '',
        ) if part)
        website = university.website or '-'
        return format_html(
            '<div style="line-height:1.5">'
            '<strong>{}</strong><br>'
            'Локация: {}<br>'
            'Сайт: {}'
            '</div>',
            university.name,
            location or '-',
            website,
        )

    @admin.action(description='Опубликовать выбранные программы')
    def mark_active(self, request, queryset):
        queryset.update(is_active=True, is_archived=False)

    @admin.action(description='Архивировать выбранные программы')
    def mark_archived(self, request, queryset):
        queryset.update(is_archived=True)

    @admin.action(description='Вернуть выбранные программы из архива')
    def mark_unarchived(self, request, queryset):
        queryset.update(is_archived=False)


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
