from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .models import City, Country, Currency, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact


@admin.register(Country)
class CountryAdmin(ModelAdmin):
    list_display = ('name', 'code', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(City)
class CityAdmin(ModelAdmin):
    list_display = ('name', 'country', 'sort_order', 'is_active')
    list_filter = ('country', 'is_active')
    search_fields = ('name', 'country__name')
    autocomplete_fields = ('country',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Currency)
class CurrencyAdmin(ModelAdmin):
    list_display = ('code', 'name', 'symbol', 'rate_to_usd', 'updated_at')
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')


class ProgramInline(TabularInline):
    model = Program
    extra = 1
    fields = ('name', 'degree', 'faculty', 'language', 'duration', 'description', 'is_active', 'is_archived')
    show_change_link = True


class RequiredDocumentInline(TabularInline):
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


@admin.register(University)
class UniversityAdmin(ModelAdmin):
    list_display = ('name', 'country', 'city', 'website', 'is_active', 'updated_at')
    list_filter = ('is_active', 'country', 'city')
    search_fields = ('name', 'legal_name', 'country__name', 'city__name', 'website', 'email')
    autocomplete_fields = ('company', 'country', 'city', 'local_currency', 'added_by')
    readonly_fields = ('logo_preview', 'cover_preview', 'program_fee_hint', 'created_at', 'updated_at')
    inlines = [ProgramInline, RequiredDocumentInline, UniversityContactInline]
    fieldsets = (
        ('Основное', {
            'fields': ('company', 'name', 'legal_name', 'country', 'city', 'local_currency', 'is_active'),
            'description': 'Если страны, города или валюты ещё нет, добавьте их через плюс рядом с полем или через раздел "ВУЗы и программы".',
        }),
        ('Контакты', {'fields': ('website', 'email', 'phone', 'address')}),
        ('Описание для клиентов', {'fields': ('description', 'admission_requirements', 'invitation_info', 'dormitory_info', 'expenses_info', 'age_limit')}),
        ('Изображения', {'fields': ('logo', 'logo_preview', 'cover_image', 'cover_preview')}),
        ('Следующий шаг', {'fields': ('program_fee_hint',)}),
        ('Внутреннее', {'fields': ('commission_info', 'custom_data', 'added_by'), 'classes': ('collapse',)}),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Логотип')
    def logo_preview(self, obj):
        if obj and obj.logo:
            return format_html('<img src="{}" style="max-width:140px; max-height:100px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />', obj.logo.url)
        return 'Логотип не загружен'

    @admin.display(description='Обложка')
    def cover_preview(self, obj):
        if obj and obj.cover_image:
            return format_html('<img src="{}" style="max-width:220px; max-height:120px; border:1px solid #e5e7eb; border-radius:8px; padding:6px; background:#fff;" />', obj.cover_image.url)
        return 'Обложка не загружена'

    @admin.display(description='Стоимость программ')
    def program_fee_hint(self, obj):
        if not obj or not obj.pk:
            return 'Сначала сохраните ВУЗ. После сохранения ниже можно добавить программы, затем открыть программу и добавить стоимость.'
        url = reverse('admin:education_programfee_add')
        return format_html(
            '<div style="line-height:1.5">Программы добавляйте в inline-блоке ниже. Стоимость добавляется в разделе '
            '<a href="{}">Стоимость программ</a>: выберите программу, валюту и суммы. '
            'Если добавили ВУЗ, обязательно добавьте хотя бы одну программу.</div>',
            url,
        )


@admin.register(Program)
class ProgramAdmin(ModelAdmin):
    list_display = ('name', 'university', 'degree', 'language', 'duration', 'is_active', 'is_archived')
    list_filter = ('degree', 'language', 'is_active', 'is_archived', 'university__country')
    search_fields = ('name', 'faculty', 'university__name', 'university__country__name')
    autocomplete_fields = ('university',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProgramFee)
class ProgramFeeAdmin(ModelAdmin):
    list_display = ('program', 'currency', 'tuition_fee', 'service_fee_usd', 'valid_from', 'valid_to')
    list_filter = ('currency', 'valid_from', 'valid_to')
    search_fields = ('program__name', 'program__university__name')
    autocomplete_fields = ('program', 'currency')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Intake)
class IntakeAdmin(ModelAdmin):
    list_display = ('title', 'program', 'start_date', 'application_deadline', 'is_active')
    list_filter = ('is_active', 'start_date', 'application_deadline')
    search_fields = ('title', 'program__name', 'program__university__name')
    autocomplete_fields = ('program',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RequiredDocument)
class RequiredDocumentAdmin(ModelAdmin):
    list_display = ('title', 'university', 'program', 'is_mandatory', 'sort_order', 'is_active')
    list_filter = ('is_mandatory', 'is_active')
    search_fields = ('title', 'university__name', 'program__name')
    autocomplete_fields = ('university', 'program')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(UniversityContact)
class UniversityContactAdmin(ModelAdmin):
    list_display = ('university', 'full_name', 'position', 'email', 'phone', 'is_active')
    list_filter = ('is_active', 'university__country')
    search_fields = ('university__name', 'full_name', 'position', 'email', 'phone')
    autocomplete_fields = ('university',)
    readonly_fields = ('created_at', 'updated_at')
