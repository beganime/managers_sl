from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display

from .models import SupportMessage


@admin.register(SupportMessage)
class SupportMessageAdmin(ModelAdmin):
    list_display = ('subject', 'user_display', 'category', 'status_badge', 'created_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('subject', 'message', 'user__email', 'user__first_name', 'user__last_name')
    readonly_fields = ('user', 'category', 'subject', 'message', 'created_at', 'updated_at')

    fieldsets = (
        ('Обращение', {
            'fields': ('user', 'category', 'subject', 'message'),
        }),
        ('Ответ администратора', {
            'fields': ('status', 'admin_note'),
        }),
        ('Системное', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @display(description='Пользователь')
    def user_display(self, obj):
        if not obj.user:
            return '—'
        full = f'{obj.user.first_name} {obj.user.last_name}'.strip()
        return full or obj.user.email

    @display(description='Статус', label=True)
    def status_badge(self, obj):
        colors = {
            'new': 'info',
            'in_progress': 'warning',
            'closed': 'success',
        }
        return obj.get_status_display(), colors.get(obj.status, 'default')