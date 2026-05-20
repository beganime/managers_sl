from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Company, Department, Office, Position


@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    list_display = ('name', 'legal_name', 'country', 'city', 'phone', 'email', 'is_active')
    list_filter = ('is_active', 'country', 'city')
    search_fields = ('name', 'legal_name', 'registration_number', 'phone', 'email')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Основное', {
            'fields': ('name', 'legal_name', 'registration_number', 'is_active')
        }),
        ('Контакты', {
            'fields': (('country', 'city'), 'address', ('phone', 'email'), 'website')
        }),
        ('Брендинг', {
            'fields': ('logo', 'stamp')
        }),
        ('Управление', {
            'fields': ('owner', 'notes')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Office)
class OfficeAdmin(ModelAdmin):
    list_display = ('name', 'company', 'country', 'city', 'director', 'phone', 'is_active')
    list_filter = ('is_active', 'company', 'country', 'city')
    search_fields = ('name', 'company__name', 'city', 'address', 'phone', 'email')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('company', 'director')
    fieldsets = (
        ('Основное', {
            'fields': ('company', 'name', 'is_active')
        }),
        ('Адрес и контакты', {
            'fields': (('country', 'city'), 'address', ('phone', 'email'), 'timezone')
        }),
        ('Управление', {
            'fields': ('director', 'notes')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Department)
class DepartmentAdmin(ModelAdmin):
    list_display = ('name', 'company', 'sort_order', 'is_active')
    list_filter = ('is_active', 'company')
    search_fields = ('name', 'company__name')
    autocomplete_fields = ('company',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Position)
class PositionAdmin(ModelAdmin):
    list_display = ('name', 'company', 'department', 'sort_order', 'is_active')
    list_filter = ('is_active', 'company', 'department')
    search_fields = ('name', 'company__name', 'department__name')
    autocomplete_fields = ('company', 'department')
    readonly_fields = ('created_at', 'updated_at')
