from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    AttendanceReminder,
    AttendanceTelegramDelivery,
    AttendanceTelegramTopic,
    AutoCloseLog,
    DailyReport,
    EmployeeTelegramAccount,
    TelegramLinkCode,
    WeeklyReport,
    WorkDay,
    WorkSession,
)


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


@admin.register(WeeklyReport)
class WeeklyReportAdmin(ModelAdmin):
    list_display = ('employee', 'period_start', 'period_end', 'office', 'telegram_sent_at', 'disk_archived_at')
    list_filter = ('company', 'office', 'period_end')
    search_fields = ('employee__email', 'employee__first_name', 'employee__last_name', 'work_done', 'next_week_plans')
    autocomplete_fields = ('company', 'office', 'employee')
    readonly_fields = ('generated_file', 'disk_path', 'disk_archived_at', 'telegram_sent_at', 'telegram_error', 'submitted_at', 'expires_at', 'created_at', 'updated_at')


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


@admin.register(AttendanceTelegramDelivery)
class AttendanceTelegramDeliveryAdmin(ModelAdmin):
    list_display = ('event_type', 'employee', 'office', 'target_message_thread_id', 'status', 'attempts', 'sent_at', 'created_at')
    list_filter = ('event_type', 'status', 'company', 'office')
    search_fields = ('event_key', 'employee__email', 'employee__first_name', 'employee__last_name', 'message')
    readonly_fields = ('event_key', 'message', 'attempts', 'last_error', 'sent_at', 'created_at', 'updated_at')


@admin.register(AttendanceTelegramTopic)
class AttendanceTelegramTopicAdmin(ModelAdmin):
    list_display = ('topic_type', 'title', 'chat_id', 'message_thread_id', 'updated_at')
    list_filter = ('topic_type',)
    search_fields = ('title', 'chat_id', 'message_thread_id')
    readonly_fields = ('configured_by_telegram_user_id', 'created_at', 'updated_at')


@admin.register(EmployeeTelegramAccount)
class EmployeeTelegramAccountAdmin(ModelAdmin):
    list_display = ('employee', 'username', 'telegram_user_id', 'is_active', 'linked_at')
    list_filter = ('is_active', 'linked_at')
    search_fields = ('employee__email', 'employee__first_name', 'employee__last_name', 'username')
    readonly_fields = ('telegram_user_id', 'chat_id', 'linked_at', 'created_at', 'updated_at')


@admin.register(TelegramLinkCode)
class TelegramLinkCodeAdmin(ModelAdmin):
    list_display = ('employee', 'expires_at', 'used_at', 'created_at')
    search_fields = ('employee__email', 'employee__first_name', 'employee__last_name')
    readonly_fields = ('code_hash', 'expires_at', 'used_at', 'created_at', 'updated_at')
