from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Application,
    Client,
    ClientActivity,
    ClientFile,
    ClientNote,
    Lead,
    LeadSource,
)


@admin.register(LeadSource)
class LeadSourceAdmin(ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = ('full_name', 'phone', 'company', 'office', 'manager', 'source', 'status', 'direction', 'created_at')
    list_filter = ('status', 'direction', 'company', 'office', 'source', 'created_at')
    search_fields = ('full_name', 'phone', 'email', 'country', 'city', 'interested_country', 'interested_program')
    autocomplete_fields = ('company', 'office', 'source', 'manager')
    readonly_fields = ('created_at', 'updated_at', 'converted_at')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Контакт', {
            'fields': ('full_name', ('phone', 'email'), ('country', 'city'))
        }),
        ('CRM', {
            'fields': ('company', 'office', 'source', 'manager', ('status', 'direction'), 'interested_country', 'interested_program')
        }),
        ('Комментарий', {
            'fields': ('comment',)
        }),
        ('Техническая информация', {
            'fields': ('submitter_ip', 'submitter_user_agent', 'submitter_referer', 'converted_at', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


class ApplicationInline(TabularInline):
    model = Application
    extra = 0
    fields = ('university_name', 'program_name', 'country', 'status', 'submitted_at', 'decision_at')
    readonly_fields = ()


class ClientNoteInline(TabularInline):
    model = ClientNote
    extra = 0
    fields = ('author', 'text', 'is_private', 'created_at')
    readonly_fields = ('created_at',)


class ClientFileInline(TabularInline):
    model = ClientFile
    extra = 0
    fields = ('title', 'file', 'file_type', 'uploaded_by', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ('full_name', 'phone', 'company', 'office', 'manager', 'status', 'is_priority', 'is_partner_client', 'created_at')
    list_filter = ('status', 'company', 'office', 'manager', 'is_priority', 'is_partner_client', 'created_at')
    search_fields = ('full_name', 'phone', 'email', 'passport_local_num', 'passport_inter_num', 'partner_name')
    autocomplete_fields = ('company', 'office', 'manager', 'shared_with', 'source_lead')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('shared_with',)
    inlines = [ApplicationInline, ClientNoteInline, ClientFileInline]
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Основная информация', {
            'fields': ('company', 'office', 'manager', 'shared_with', 'source_lead', ('status', 'is_priority'))
        }),
        ('Контакты', {
            'fields': ('full_name', ('phone', 'email'), 'dob', 'citizenship', 'city')
        }),
        ('Адреса', {
            'fields': ('address', 'address_registration')
        }),
        ('Паспорт', {
            'fields': ('passport_local_num', 'passport_inter_num', 'passport_issued_by', 'passport_issued_date')
        }),
        ('Партнёр', {
            'fields': ('is_partner_client', 'partner_name')
        }),
        ('Комментарии и доп. данные', {
            'fields': ('comments', 'custom_data')
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Application)
class ApplicationAdmin(ModelAdmin):
    list_display = ('client', 'university_name', 'program_name', 'country', 'manager', 'status', 'submitted_at', 'created_at')
    list_filter = ('status', 'company', 'office', 'country', 'degree', 'language', 'created_at')
    search_fields = ('client__full_name', 'client__phone', 'university_name', 'program_name', 'country')
    autocomplete_fields = ('client', 'company', 'office', 'manager')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(ClientActivity)
class ClientActivityAdmin(ModelAdmin):
    list_display = ('client', 'activity_type', 'title', 'manager', 'due_at', 'completed_at', 'created_at')
    list_filter = ('activity_type', 'completed_at', 'created_at')
    search_fields = ('client__full_name', 'client__phone', 'title', 'description')
    autocomplete_fields = ('client', 'manager')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClientNote)
class ClientNoteAdmin(ModelAdmin):
    list_display = ('client', 'author', 'is_private', 'created_at')
    list_filter = ('is_private', 'created_at')
    search_fields = ('client__full_name', 'client__phone', 'text')
    autocomplete_fields = ('client', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ClientFile)
class ClientFileAdmin(ModelAdmin):
    list_display = ('title', 'client', 'application', 'file_type', 'uploaded_by', 'created_at')
    list_filter = ('file_type', 'created_at')
    search_fields = ('title', 'client__full_name', 'client__phone', 'comment')
    autocomplete_fields = ('client', 'application', 'uploaded_by')
    readonly_fields = ('created_at', 'updated_at')
