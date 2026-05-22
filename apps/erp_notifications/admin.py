from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import DeviceToken, Notification, NotificationLog, NotificationTemplate
from .services import send_notification


class NotificationLogInline(TabularInline):
    model = NotificationLog
    extra = 0
    can_delete = False
    readonly_fields = (
        'device_token',
        'channel',
        'status',
        'provider',
        'recipient',
        'request_data',
        'response_data',
        'error_message',
        'sent_at',
        'created_at',
    )
    fields = readonly_fields


@admin.register(DeviceToken)
class DeviceTokenAdmin(ModelAdmin):
    list_display = ('user', 'platform', 'device_name', 'company', 'office', 'is_active', 'last_seen_at')
    list_filter = ('platform', 'is_active', 'company', 'office', 'last_seen_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'token', 'device_name')
    autocomplete_fields = ('company', 'office', 'user')
    readonly_fields = ('last_seen_at', 'created_at', 'updated_at')


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(ModelAdmin):
    list_display = ('name', 'code', 'company', 'notification_type', 'channel', 'send_in_app', 'send_push', 'send_email', 'is_active')
    list_filter = ('notification_type', 'channel', 'send_in_app', 'send_push', 'send_email', 'is_active', 'company')
    search_fields = ('name', 'code', 'title_template', 'body_template', 'company__name')
    autocomplete_fields = ('company', 'created_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ('title', 'recipient', 'notification_type', 'channel', 'priority', 'status', 'created_at')
    list_filter = ('notification_type', 'channel', 'priority', 'status', 'company', 'office', 'created_at')
    search_fields = ('title', 'body', 'recipient__email', 'recipient__first_name', 'recipient__last_name')
    autocomplete_fields = ('company', 'office', 'recipient', 'sender', 'template')
    raw_id_fields = ('content_type',)
    readonly_fields = ('queued_at', 'sent_at', 'read_at', 'failed_at', 'error_message', 'created_at', 'updated_at')
    inlines = [NotificationLogInline]
    date_hierarchy = 'created_at'

    @admin.action(description='Queue selected notifications')
    def queue_notifications(self, request, queryset):
        for notification in queryset:
            notification.queue()

    @admin.action(description='Send selected notifications now')
    def send_notifications(self, request, queryset):
        for notification in queryset.select_related('recipient'):
            send_notification(notification)

    @admin.action(description='Mark selected notifications as read')
    def mark_read(self, request, queryset):
        for notification in queryset:
            notification.mark_read()

    actions = ('queue_notifications', 'send_notifications', 'mark_read')


@admin.register(NotificationLog)
class NotificationLogAdmin(ModelAdmin):
    list_display = ('notification', 'channel', 'status', 'provider', 'recipient', 'sent_at', 'created_at')
    list_filter = ('channel', 'status', 'provider', 'sent_at', 'created_at')
    search_fields = ('notification__title', 'recipient', 'error_message', 'provider')
    autocomplete_fields = ('notification', 'device_token')
    readonly_fields = ('created_at',)
