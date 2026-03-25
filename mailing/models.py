# mailing/models.py
from django.db import models
from django.conf import settings

class EmailTemplate(models.Model):
    CATEGORY_CHOICES = (
        ('info',      'Информационное'),
        ('promo',     'Акция / Предложение'),
        ('reminder',  'Напоминание'),
        ('welcome',   'Приветственное'),
        ('custom',    'Произвольное'),
    )
    title      = models.CharField('Название шаблона', max_length=255)
    category   = models.CharField('Категория', max_length=20, choices=CATEGORY_CHOICES, default='custom')
    subject    = models.CharField('Тема письма', max_length=255)
    body_html  = models.TextField('HTML-тело письма', help_text='Используйте {{first_name}}, {{last_name}}, {{email}}, {{office}} как переменные')
    body_text  = models.TextField('Текстовое тело (запасной вариант)', blank=True, help_text='Отображается если HTML не поддерживается')
    is_active  = models.BooleanField('Активен', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name        = 'Шаблон письма'
        verbose_name_plural = 'Шаблоны писем'
        ordering            = ['-created_at']


class MailingCampaign(models.Model):
    STATUS_CHOICES = (
        ('draft',     'Черновик'),
        ('scheduled', 'Запланирована'),
        ('sending',   'Отправляется'),
        ('done',      'Завершена'),
        ('error',     'Ошибка'),
    )

    RECIPIENT_TYPE_CHOICES = (
        ('all_clients',      'Все клиенты (Вся база)'),
        ('all_staff',        'Все сотрудники (Вся команда)'),
        ('specific_clients', 'Выбрать клиентов вручную'),
        ('specific_staff',   'Выбрать сотрудников вручную'),
        ('clients_status',   'Клиенты по статусу'),
        ('custom_emails',    'Ввести любые email вручную'),
    )

    title           = models.CharField('Название кампании', max_length=255)
    template        = models.ForeignKey(EmailTemplate, on_delete=models.PROTECT, verbose_name='Шаблон письма', related_name='campaigns')
    recipient_type  = models.CharField('Тип получателей', max_length=30, choices=RECIPIENT_TYPE_CHOICES, default='all_clients')
    
    # === НОВЫЕ ПОЛЯ ДЛЯ КРАСИВОГО ВЫБОРА ===
    specific_clients = models.ManyToManyField('clients.Client', blank=True, verbose_name='Конкретные клиенты')
    specific_staff   = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, verbose_name='Конкретные сотрудники')
    
    client_status   = models.CharField('Статус клиентов', max_length=20, blank=True, help_text='Заполнять при типе "Клиенты по статусу"')
    custom_emails   = models.TextField('Произвольные email (через запятую или перенос строки)', blank=True)
    
    created_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='mailing_campaigns', verbose_name='Кто создал')
    status          = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='draft')
    total_sent      = models.PositiveIntegerField('Отправлено писем', default=0)
    total_failed    = models.PositiveIntegerField('Ошибок отправки',  default=0)
    error_log       = models.TextField('Лог ошибок', blank=True)

    scheduled_at    = models.DateTimeField('Запланировано на', null=True, blank=True)
    started_at      = models.DateTimeField('Начало отправки',  null=True, blank=True)
    finished_at     = models.DateTimeField('Конец отправки',   null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title} [{self.get_status_display()}]'

    class Meta:
        verbose_name        = 'Рассылка'
        verbose_name_plural = 'Рассылки'
        ordering            = ['-created_at']


class MailingLog(models.Model):
    campaign   = models.ForeignKey(MailingCampaign, on_delete=models.CASCADE, related_name='logs', verbose_name='Кампания')
    email      = models.EmailField('Email получателя')
    recipient_name = models.CharField('Имя получателя', max_length=255, blank=True)
    is_success = models.BooleanField('Успешно', default=True)
    error_msg  = models.TextField('Сообщение об ошибке', blank=True)
    sent_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Лог отправки'
        verbose_name_plural = 'История отправок'
        ordering            = ['-sent_at']

    def __str__(self):
        status = '✓' if self.is_success else '✗'
        return f'{status} {self.email} — {self.campaign.title}'