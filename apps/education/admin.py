from django.contrib import admin
from unfold.admin import ModelAdmin

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


@admin.register(University)
class UniversityAdmin(ModelAdmin):
    list_display = ('name', 'country', 'city', 'website', 'is_active', 'updated_at')
    list_filter = ('is_active', 'country', 'city')
    search_fields = ('name', 'legal_name', 'country__name', 'city__name', 'website', 'email')
    autocomplete_fields = ('company', 'country', 'city', 'local_currency', 'added_by')
    readonly_fields = ('created_at', 'updated_at')


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
