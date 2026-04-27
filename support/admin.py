from django.contrib import admin, messages
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from .models import SupportMessage


@admin.register(SupportMessage)
class SupportMessageAdmin(ModelAdmin):
    list_display = ('subject_card', 'user_display', 'category_badge', 'status_badge', 'attachment_preview', 'created_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('subject', 'message', 'admin_note', 'user__email', 'user__first_name', 'user__last_name')
    readonly_fields = ('user', 'category', 'subject', 'message', 'photo_preview_large', 'file_link', 'created_at', 'updated_at')
    actions = ('mark_in_progress', 'mark_closed', 'mark_new')

    fieldsets = (
        ('Обращение сотрудника', {'fields': ('user', 'category', 'subject', 'message')}),
        ('Вложения из приложения', {'fields': ('photo_preview_large', 'file_link')}),
        ('Ответ администратора', {
            'fields': ('status', 'admin_note'),
            'description': 'Ответ пишется в поле “Заметка администратора / ответ”. В мобильном приложении сотрудник увидит этот текст в истории обращений.',
        }),
        ('Системное', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @display(description='Обращение')
    def subject_card(self, obj):
        return format_html(
            '<div style="min-width:260px"><div style="font-weight:800;font-size:14px;margin-bottom:4px">{}</div><div style="font-size:12px;color:#64748b;max-width:420px;white-space:normal">{}</div></div>',
            obj.subject,
            (obj.message[:140] + '…') if len(obj.message or '') > 140 else (obj.message or '—'),
        )

    @display(description='Пользователь')
    def user_display(self, obj):
        if not obj.user:
            return '—'
        full = f'{obj.user.first_name} {obj.user.last_name}'.strip()
        label = full or obj.user.email
        return format_html('<div><b>{}</b><br><span style="color:#64748b;font-size:12px">{}</span></div>', label, obj.user.email)

    @display(description='Категория', label=True)
    def category_badge(self, obj):
        colors = {'support': 'info', 'feedback': 'success', 'bug': 'danger', 'idea': 'warning', 'admin': 'primary'}
        return obj.get_category_display(), colors.get(obj.category, 'default')

    @display(description='Статус', label=True)
    def status_badge(self, obj):
        colors = {'new': 'info', 'in_progress': 'warning', 'closed': 'success'}
        return obj.get_status_display(), colors.get(obj.status, 'default')

    @display(description='Вложения')
    def attachment_preview(self, obj):
        parts = []
        if obj.photo:
            parts.append(f'<a href="{obj.photo.url}" target="_blank">📷 Фото</a>')
        if obj.file:
            parts.append(f'<a href="{obj.file.url}" target="_blank">📎 Файл</a>')
        return format_html('<br>'.join(parts)) if parts else '—'

    @display(description='Фото')
    def photo_preview_large(self, obj):
        if not obj.photo:
            return 'Фото не прикреплено'
        return format_html(
            '<a href="{}" target="_blank"><img src="{}" style="max-width:420px;max-height:320px;border-radius:16px;border:1px solid #e5e7eb;object-fit:cover" /></a>',
            obj.photo.url,
            obj.photo.url,
        )

    @display(description='Файл')
    def file_link(self, obj):
        if not obj.file:
            return 'Файл не прикреплён'
        return format_html('<a href="{}" target="_blank" style="font-weight:700">📎 Скачать / открыть файл</a>', obj.file.url)

    @action(description='Взять в работу')
    def mark_in_progress(self, request, queryset):
        count = queryset.update(status='in_progress')
        self.message_user(request, f'Взято в работу: {count}', messages.SUCCESS)

    @action(description='Закрыть обращения')
    def mark_closed(self, request, queryset):
        count = queryset.update(status='closed')
        self.message_user(request, f'Закрыто: {count}', messages.SUCCESS)

    @action(description='Вернуть в новые')
    def mark_new(self, request, queryset):
        count = queryset.update(status='new')
        self.message_user(request, f'Возвращено в новые: {count}', messages.SUCCESS)