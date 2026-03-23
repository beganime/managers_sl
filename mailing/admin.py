# mailing/admin.py
from django.contrib import admin, messages
from django.db import models
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpRequest

from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import EmailTemplate, MailingCampaign, MailingLog
from .services import send_campaign, _get_recipients


# ─── Шаблоны писем ───────────────────────────────────────────────────────────

@admin.register(EmailTemplate)
class EmailTemplateAdmin(ModelAdmin):
    list_display  = ('title', 'category_badge', 'is_active', 'updated_at')
    list_filter   = ('category', 'is_active')
    search_fields = ('title', 'subject')

    fieldsets = (
        ('Основное', {
            'fields': ('title', 'category', 'is_active'),
            'classes': ('tab-tabular',),
        }),
        ('Содержание письма', {
            'fields': ('subject', 'body_html', 'body_text'),
            'description': (
                'Доступные переменные: '
                '<code>{{first_name}}</code> <code>{{last_name}}</code> '
                '<code>{{email}}</code> <code>{{office}}</code>'
            ),
        }),
    )

    formfield_overrides = {
        models.TextField: {'widget': WysiwygWidget},
    }

    @display(description='Категория', label=True)
    def category_badge(self, obj):
        colors = {
            'info':     'info',
            'promo':    'warning',
            'reminder': 'danger',
            'welcome':  'success',
            'custom':   'default',
        }
        return obj.get_category_display(), colors.get(obj.category, 'default')


# ─── Лог отправки (строчный) ─────────────────────────────────────────────────

class MailingLogInline(TabularInline):
    model      = MailingLog
    extra      = 0
    max_num    = 0      # только просмотр
    fields     = ('email', 'recipient_name', 'is_success', 'error_msg', 'sent_at')
    readonly_fields = ('email', 'recipient_name', 'is_success', 'error_msg', 'sent_at')
    can_delete = False
    verbose_name_plural = 'История отправок'


# ─── Кампании рассылки ────────────────────────────────────────────────────────

@admin.register(MailingCampaign)
class MailingCampaignAdmin(ModelAdmin):
    inlines       = [MailingLogInline]
    list_display  = (
        'title', 'template', 'recipient_type_badge',
        'status_badge', 'progress_display', 'created_by', 'created_at',
    )
    list_filter   = ('status', 'recipient_type', 'template')
    search_fields = ('title', 'custom_emails')
    readonly_fields = (
        'status', 'total_sent', 'total_failed',
        'error_log', 'started_at', 'finished_at',
    )
    actions = ['action_send_now']

    fieldsets = (
        ('Кампания', {
            'fields': ('title', 'template'),
            'classes': ('tab-tabular',),
        }),
        ('Получатели', {
            'fields': ('recipient_type', 'client_status', 'custom_emails'),
            'description': (
                '<b>Все клиенты</b> — берёт email из карточек клиентов.<br>'
                '<b>Все сотрудники</b> — берёт email из профилей пользователей.<br>'
                '<b>По статусу</b> — нужно заполнить поле "Статус клиентов".<br>'
                '<b>Произвольные</b> — введите адреса через запятую или перенос строки.'
            ),
        }),
        ('Статус (только чтение)', {
            'fields': (
                'status',
                ('total_sent', 'total_failed'),
                ('started_at', 'finished_at'),
                'error_log',
            ),
            'classes': ('collapse',),
        }),
    )

    # ── Кастомный URL для отправки ────────────────────────────────────────────
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:campaign_id>/send/',
                self.admin_site.admin_view(self.send_campaign_view),
                name='mailing_send_campaign',
            ),
            path(
                '<int:campaign_id>/preview/',
                self.admin_site.admin_view(self.preview_recipients_view),
                name='mailing_preview_recipients',
            ),
        ]
        return custom + urls

    def send_campaign_view(self, request: HttpRequest, campaign_id: int):
        """POST → запускает рассылку прямо в запросе (синхронно)."""
        campaign = get_object_or_404(MailingCampaign, pk=campaign_id)
        if campaign.status in ('sending', 'done'):
            self.message_user(
                request,
                f'Рассылка «{campaign.title}» уже {campaign.get_status_display().lower()}.',
                messages.WARNING,
            )
            return redirect('admin:mailing_mailingcampaign_change', campaign_id)

        try:
            send_campaign(campaign)
            self.message_user(
                request,
                f'✅ Рассылка завершена: {campaign.total_sent} отправлено, {campaign.total_failed} ошибок.',
                messages.SUCCESS if campaign.total_failed == 0 else messages.WARNING,
            )
        except Exception as e:
            self.message_user(request, f'❌ Ошибка рассылки: {e}', messages.ERROR)

        return redirect('admin:mailing_mailingcampaign_change', campaign_id)

    def preview_recipients_view(self, request: HttpRequest, campaign_id: int):
        """Показывает список получателей перед отправкой."""
        campaign   = get_object_or_404(MailingCampaign, pk=campaign_id)
        recipients = _get_recipients(campaign)
        emails     = [r['email'] for r in recipients]
        self.message_user(
            request,
            f'Получателей: {len(emails)}. Примеры: {", ".join(emails[:10])}{"..." if len(emails) > 10 else ""}',
            messages.INFO,
        )
        return redirect('admin:mailing_mailingcampaign_change', campaign_id)

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    # ── Групповое действие ────────────────────────────────────────────────────
    @action(description='📨 Отправить выбранные рассылки')
    def action_send_now(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, 'Только суперадмин может запускать рассылки.', messages.ERROR)
            return
        total_ok, total_err = 0, 0
        for campaign in queryset.filter(status__in=('draft', 'error')):
            send_campaign(campaign)
            total_ok  += campaign.total_sent
            total_err += campaign.total_failed
        self.message_user(
            request,
            f'Итого: {total_ok} писем отправлено, {total_err} ошибок.',
            messages.SUCCESS if total_err == 0 else messages.WARNING,
        )

    # ── Отображение ───────────────────────────────────────────────────────────
    @display(description='Получатели', label=True)
    def recipient_type_badge(self, obj):
        colors = {
            'all_clients':    'info',
            'all_staff':      'success',
            'clients_status': 'warning',
            'custom_emails':  'default',
        }
        return obj.get_recipient_type_display(), colors.get(obj.recipient_type, 'default')

    @display(description='Статус', label=True)
    def status_badge(self, obj):
        colors = {
            'draft':     'default',
            'scheduled': 'info',
            'sending':   'warning',
            'done':      'success',
            'error':     'danger',
        }
        return obj.get_status_display(), colors.get(obj.status, 'default')

    @display(description='Прогресс')
    def progress_display(self, obj):
        if obj.status == 'draft':
            return format_html(
                '<a href="{}" class="text-blue-600 font-bold text-xs">👁 Предпросмотр</a>',
                f'/admin/mailing/mailingcampaign/{obj.pk}/preview/',
            )
        if obj.status in ('done', 'error'):
            color = 'text-green-600' if obj.status == 'done' else 'text-red-600'
            return format_html(
                '<span class="{}">{} ✓ / {} ✗</span>',
                color, obj.total_sent, obj.total_failed,
            )
        return '—'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['send_url'] = f'/admin/mailing/mailingcampaign/{object_id}/send/'
        extra_context['preview_url'] = f'/admin/mailing/mailingcampaign/{object_id}/preview/'
        return super().change_view(request, object_id, form_url, extra_context)


# ─── Лог (отдельно, только чтение) ───────────────────────────────────────────

@admin.register(MailingLog)
class MailingLogAdmin(ModelAdmin):
    list_display  = ('campaign', 'email', 'recipient_name', 'success_badge', 'sent_at')
    list_filter   = ('is_success', 'campaign')
    search_fields = ('email', 'recipient_name')

    def has_add_permission(self, request):    return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    @display(description='Результат', label=True, boolean=True)
    def success_badge(self, obj):
        return obj.is_success