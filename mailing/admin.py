# mailing/admin.py
from django.contrib import admin, messages
from django.db import models
from django.shortcuts import redirect

from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import EmailTemplate, MailingCampaign, MailingLog
from .services import send_campaign, send_test_email

@admin.register(EmailTemplate)
class EmailTemplateAdmin(ModelAdmin):
    list_display  = ('title', 'category_badge', 'is_active', 'updated_at')
    list_filter   = ('category', 'is_active')
    search_fields = ('title', 'subject')

    formfield_overrides = {
        models.TextField: {'widget': WysiwygWidget},
    }

    @display(description='Категория', label=True)
    def category_badge(self, obj):
        colors = {'info': 'info', 'promo': 'warning', 'reminder': 'danger', 'welcome': 'success', 'custom': 'default'}
        return obj.get_category_display(), colors.get(obj.category, 'default')


class MailingLogInline(TabularInline):
    model      = MailingLog
    extra      = 0
    max_num    = 0
    readonly_fields = ('email', 'recipient_name', 'is_success', 'error_msg', 'sent_at')
    can_delete = False


@admin.register(MailingCampaign)
class MailingCampaignAdmin(ModelAdmin):
    inlines       = [MailingLogInline]
    list_display  = ('title', 'template', 'recipient_type_badge', 'status_badge', 'created_at')
    list_filter   = ('status', 'recipient_type')
    readonly_fields = ('status', 'total_sent', 'total_failed', 'error_log', 'started_at', 'finished_at')
    
    # === МАГИЯ КРАСИВОЙ АДМИНКИ (ДВЕ КОЛОНКИ ДЛЯ ВЫБОРА) ===
    filter_horizontal = ('specific_clients', 'specific_staff')

    fieldsets = (
        ('1. Основные настройки', {
            'fields': ('title', 'template', 'recipient_type'),
        }),
        ('2. Точный выбор получателей', {
            'fields': ('specific_clients', 'specific_staff', 'client_status', 'custom_emails'),
            'classes': ('collapse',),
            'description': 'Заполняйте эти поля ТОЛЬКО если выбрали соответствующий тип получателей выше.',
        }),
        ('3. Статистика (Автоматически)', {
            'fields': ('status', 'total_sent', 'total_failed', 'error_log', 'started_at', 'finished_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['send_newsletters_now']
    actions_detail = ['test_send', 'send_now_detail']

    @action(description="🚀 Отправить выбранные рассылки массово")
    def send_newsletters_now(self, request, queryset):
        count = 0
        for campaign in queryset:
            if campaign.status not in ('sending', 'done'):
                send_campaign(campaign)
                count += 1
        self.message_user(request, f"Успешно запущена отправка для {count} кампаний.", messages.SUCCESS)

    @action(description="🚀 ЗАПУСТИТЬ РАССЫЛКУ СЕЙЧАС")
    def send_now_detail(self, request, object_id):
        campaign = self.get_object(request, object_id)
        if campaign.status in ('sending', 'done'):
            self.message_user(request, "Эта рассылка уже отправлена!", level=messages.WARNING)
        else:
            try:
                send_campaign(campaign)
                self.message_user(request, f"Рассылка завершена! Отправлено: {campaign.total_sent}, Ошибок: {campaign.total_failed}", level=messages.SUCCESS)
            except Exception as e:
                self.message_user(request, f"Критическая ошибка: {str(e)}", level=messages.ERROR)
        return redirect(request.META.get('HTTP_REFERER', '.'))

    @action(description="🛠 ТЕСТОВАЯ ОТПРАВКА (на мой email)")
    def test_send(self, request, object_id):
        campaign = self.get_object(request, object_id)
        admin_email = request.user.email
        
        if not admin_email:
            self.message_user(request, "У вашего аккаунта не указан email!", level=messages.ERROR)
            return redirect(request.META.get('HTTP_REFERER', '.'))

        try:
            send_test_email(campaign, admin_email)
            self.message_user(request, f"Тестовое письмо успешно отправлено на {admin_email}. ПРОВЕРЬТЕ ПАПКУ СПАМ!", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Ошибка SMTP: {str(e)}", level=messages.ERROR)
            
        return redirect(request.META.get('HTTP_REFERER', '.'))

    @display(description='Тип получателей', label=True)
    def recipient_type_badge(self, obj):
        return obj.get_recipient_type_display(), 'info'

    @display(description='Статус', label=True)
    def status_badge(self, obj):
        colors = {'draft': 'default', 'scheduled': 'info', 'sending': 'warning', 'done': 'success', 'error': 'danger'}
        return obj.get_status_display(), colors.get(obj.status, 'default')


@admin.register(MailingLog)
class MailingLogAdmin(ModelAdmin):
    list_display  = ('campaign', 'email', 'success_badge', 'sent_at')
    list_filter   = ('is_success',)
    search_fields = ('email',)
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False

    @display(description='Успешно', label=True, boolean=True)
    def success_badge(self, obj):
        return obj.is_success