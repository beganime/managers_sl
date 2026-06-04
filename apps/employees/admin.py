from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import EmployeeAccess, EmployeeProfile, EmployeeRating, EmployeeRole


@admin.register(EmployeeRole)
class EmployeeRoleAdmin(ModelAdmin):
    list_display = ('name', 'code', 'role_type', 'is_active')
    list_filter = ('role_type', 'is_active')
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created_at', 'updated_at')


class EmployeeAccessInline(admin.StackedInline):
    model = EmployeeAccess
    can_delete = False
    extra = 0
    fieldsets = (
        ('Видимость данных', {'fields': ('can_see_all_company', 'can_see_all_office')}),
        ('Права управления', {'fields': ('can_manage_finance', 'can_manage_hr', 'can_manage_documents', 'can_manage_catalog')}),
        ('Рейтинг и рабочий день', {
            'fields': (
                'can_be_in_leaderboard',
                'rating_priority_enabled',
                'rating_priority_level',
                'rating_priority_note',
                'must_track_workday',
            )
        }),
    )


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(ModelAdmin):
    list_display = ('user', 'company', 'office', 'department', 'position', 'role', 'work_status', 'rating', 'is_active')
    list_filter = ('company', 'office', 'department', 'role', 'work_status', 'is_active')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'company__name', 'office__name')
    autocomplete_fields = ('user', 'company', 'office', 'department', 'position', 'role')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [EmployeeAccessInline]
    fieldsets = (
        ('Сотрудник', {
            'fields': ('user', 'is_active', 'work_status')
        }),
        ('Организация', {
            'fields': ('company', 'office', 'department', 'position', 'role')
        }),
        ('Работа', {
            'fields': ('hire_date', 'fired_date')
        }),
        ('Оплата и рейтинг', {
            'fields': ('salary_type', ('fixed_salary', 'commission_percent'), 'rating')
        }),
        ('Заметки', {
            'fields': ('notes',)
        }),
        ('Системная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(EmployeeAccess)
class EmployeeAccessAdmin(ModelAdmin):
    list_display = (
        'employee',
        'can_see_all_company',
        'can_see_all_office',
        'can_manage_finance',
        'can_manage_hr',
        'can_be_in_leaderboard',
        'rating_priority_enabled',
        'rating_priority_level',
        'must_track_workday',
    )
    list_filter = (
        'can_see_all_company',
        'can_see_all_office',
        'can_manage_finance',
        'can_manage_hr',
        'can_be_in_leaderboard',
        'rating_priority_enabled',
        'must_track_workday',
    )
    search_fields = ('employee__user__email', 'employee__user__first_name', 'employee__user__last_name')
    autocomplete_fields = ('employee',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Сотрудник', {'fields': ('employee',)}),
        ('Видимость данных', {'fields': ('can_see_all_company', 'can_see_all_office')}),
        ('Права управления', {'fields': ('can_manage_finance', 'can_manage_hr', 'can_manage_documents', 'can_manage_catalog')}),
        ('Рейтинг и рабочий день', {
            'fields': (
                'can_be_in_leaderboard',
                'rating_priority_enabled',
                'rating_priority_level',
                'rating_priority_note',
                'must_track_workday',
            )
        }),
        ('Аудит', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(EmployeeRating)
class EmployeeRatingAdmin(ModelAdmin):
    list_display = ('employee', 'date', 'score', 'source')
    list_filter = ('date', 'source')
    search_fields = ('employee__user__email', 'employee__user__first_name', 'employee__user__last_name', 'comment')
    autocomplete_fields = ('employee',)
    readonly_fields = ('created_at', 'updated_at')
