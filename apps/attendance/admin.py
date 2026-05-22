from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import AttendanceReminder, AutoCloseLog, DailyReport, WorkDay, WorkSession


class WorkSessionInline(TabularInline):
    model = WorkSession
    extra = 0
    fields = ('started_at', 'ended_at', 'duration_seconds', 'is_active', 'start_note', 'end_note')
    readonly_fields = ('duration_seconds',)


@admin.register(WorkDay)
class WorkDayAdmin(ModelAdmin):
    list_display = ('employee', 'date', 'company', 'office', 'status', 'started_at', 'closed_at', 'total_work_hours')
    list_filter = ('status', 'company', 'office', 'date')
    search_fields = ('employee__email', 'employee__first_name', 'employee__last_name', 'comment')
    autocomplete_fields = ('company', 'office', 'employee')
    readonly_fields = ('total_work_seconds', 'started_at', 'closed_at', 'auto_closed_at', 'created_at', 'updated_at')
    date_hierarchy = 'date'
    inlines = [WorkSessionInline]

    @admin.action(description='Close selected workdays')
    def close_workdays(self, request, queryset):
        for workday in queryset.select_related('employee', 'company', 'office'):
            workday.close(user=request.user, comment='Closed from admin.')

    @admin.action(description='Auto close selected workdays')
    def auto_close_workdays(self, request, queryset):
        for workday in queryset.select_related('employee', 'company', 'office'):
            workday.close(user=request.user, comment='Auto closed from admin.', auto=True)

    actions = ('close_workdays', 'auto_close_workdays')


@admin.register(WorkSession)
class WorkSessionAdmin(ModelAdmin):
    list_display = ('employee', 'workday', 'started_at', 'ended_at', 'duration_seconds', 'is_active')
    list_filter = ('is_active', 'started_at')
    search_fields = ('employee__email', 'employee__first_name', 'employee__last_name', 'start_note', 'end_note')
    autocomplete_fields = ('workday', 'employee')
    readonly_fields = ('duration_seconds', 'created_at', 'updated_at')
    date_hierarchy = 'started_at'


@admin.register(DailyReport)
class DailyReportAdmin(ModelAdmin):
    list_display = ('employee', 'date', 'company', 'office', 'submitted_at', 'leads_processed', 'deals_closed')
    list_filter = ('company', 'office', 'date', 'submitted_at')
    search_fields = ('employee__email', 'employee__first_name', 'employee__last_name', 'content', 'results', 'plans')
    autocomplete_fields = ('workday', 'company', 'office', 'employee')
    readonly_fields = ('submitted_at', 'created_at', 'updated_at')
    date_hierarchy = 'date'


@admin.register(AttendanceReminder)
class AttendanceReminderAdmin(ModelAdmin):
    list_display = ('reminder_type', 'company', 'office', 'employee', 'scheduled_time', 'is_active', 'last_sent_at')
    list_filter = ('is_active', 'reminder_type', 'company', 'office')
    search_fields = ('message', 'employee__email', 'company__name', 'office__name')
    autocomplete_fields = ('company', 'office', 'employee', 'created_by')
    readonly_fields = ('last_sent_at', 'created_at', 'updated_at')


@admin.register(AutoCloseLog)
class AutoCloseLogAdmin(ModelAdmin):
    list_display = ('employee', 'workday', 'company', 'office', 'success', 'previous_status', 'created_at')
    list_filter = ('success', 'company', 'office', 'created_at')
    search_fields = ('employee__email', 'reason', 'error_message')
    autocomplete_fields = ('workday', 'company', 'office', 'employee')
    readonly_fields = ('created_at', 'updated_at')
