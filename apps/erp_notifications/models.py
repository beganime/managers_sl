from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.template import Context, Template
from django.utils import timezone as django_timezone

from apps.core.models import ActiveModel, TimeStampedModel
from apps.organizations.models import Company, Office


class DeviceToken(TimeStampedModel, ActiveModel):
    PLATFORM_IOS = 'ios'
    PLATFORM_ANDROID = 'android'
    PLATFORM_WEB = 'web'
    PLATFORM_UNKNOWN = 'unknown'
    PLATFORM_CHOICES = (
        (PLATFORM_IOS, 'iOS'),
        (PLATFORM_ANDROID, 'Android'),
        (PLATFORM_WEB, 'Web'),
        (PLATFORM_UNKNOWN, 'Unknown'),
    )

    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='erp_device_tokens',
        null=True,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='erp_device_tokens',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE, related_name='erp_device_tokens')
    token = models.TextField('Device token', unique=True)
    platform = models.CharField('Platform', max_length=20, choices=PLATFORM_CHOICES, default=PLATFORM_UNKNOWN, db_index=True)
    device_name = models.CharField('Device name', max_length=255, blank=True)
    app_version = models.CharField('App version', max_length=50, blank=True)
    locale = models.CharField('Locale', max_length=32, blank=True)
    timezone = models.CharField('Timezone', max_length=64, blank=True)
    last_seen_at = models.DateTimeField('Last seen at', default=django_timezone.now, db_index=True)

    class Meta:
        verbose_name = 'ERP device token'
        verbose_name_plural = 'ERP device tokens'
        ordering = ['-last_seen_at']
        indexes = [
            models.Index(fields=['company', 'office', 'is_active']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['platform', 'is_active']),
        ]

    def __str__(self):
        return f'{self.user} - {self.platform}'

    def touch(self, save=True):
        self.is_active = True
        self.last_seen_at = django_timezone.now()
        if save:
            self.save(update_fields=['is_active', 'last_seen_at', 'updated_at'])
        return self


class NotificationTemplate(TimeStampedModel, ActiveModel):
    TYPE_ATTENDANCE = 'attendance'
    TYPE_TASK = 'task'
    TYPE_DOCUMENT = 'document'
    TYPE_PAYMENT = 'payment'
    TYPE_SYSTEM = 'system'
    TYPE_KNOWLEDGE = 'knowledge'
    TYPE_CHOICES = (
        (TYPE_ATTENDANCE, 'Attendance'),
        (TYPE_TASK, 'Task'),
        (TYPE_DOCUMENT, 'Document'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_SYSTEM, 'System'),
        (TYPE_KNOWLEDGE, 'Knowledge'),
    )

    CHANNEL_IN_APP = 'in_app'
    CHANNEL_PUSH = 'push'
    CHANNEL_EMAIL = 'email'
    CHANNEL_CHOICES = (
        (CHANNEL_IN_APP, 'In-app'),
        (CHANNEL_PUSH, 'Push'),
        (CHANNEL_EMAIL, 'Email'),
    )

    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='erp_notification_templates',
        null=True,
        blank=True,
    )
    code = models.SlugField('Code', max_length=100, db_index=True)
    name = models.CharField('Name', max_length=255)
    notification_type = models.CharField('Notification type', max_length=32, choices=TYPE_CHOICES, default=TYPE_SYSTEM, db_index=True)
    channel = models.CharField('Default channel', max_length=32, choices=CHANNEL_CHOICES, default=CHANNEL_IN_APP, db_index=True)
    title_template = models.CharField('Title template', max_length=255)
    body_template = models.TextField('Body template', blank=True)
    data_template = models.JSONField('Data template', default=dict, blank=True)
    send_in_app = models.BooleanField('Send in-app', default=True)
    send_push = models.BooleanField('Send push', default=True)
    send_email = models.BooleanField('Send email', default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='erp_notification_templates_created',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'ERP notification template'
        verbose_name_plural = 'ERP notification templates'
        ordering = ['company__name', 'code']
        unique_together = [('company', 'code')]
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['notification_type', 'channel']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return self.name

    def render_text(self, template_string, context):
        if not template_string:
            return ''
        return Template(template_string).render(Context(context or {})).strip()

    def render_data(self, context):
        rendered = {}
        for key, value in (self.data_template or {}).items():
            rendered[key] = self.render_text(value, context) if isinstance(value, str) else value
        return rendered

    def render(self, context=None):
        context = context or {}
        return {
            'title': self.render_text(self.title_template, context),
            'body': self.render_text(self.body_template, context),
            'data': self.render_data(context),
        }


class Notification(TimeStampedModel):
    PRIORITY_LOW = 'low'
    PRIORITY_NORMAL = 'normal'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'
    PRIORITY_CHOICES = (
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_NORMAL, 'Normal'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    )

    STATUS_NEW = 'new'
    STATUS_QUEUED = 'queued'
    STATUS_SENT = 'sent'
    STATUS_READ = 'read'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (STATUS_NEW, 'New'),
        (STATUS_QUEUED, 'Queued'),
        (STATUS_SENT, 'Sent'),
        (STATUS_READ, 'Read'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.CASCADE,
        related_name='erp_notifications',
        null=True,
        blank=True,
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='erp_notifications',
        null=True,
        blank=True,
    )
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Recipient', on_delete=models.CASCADE, related_name='erp_notifications')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Sender',
        on_delete=models.SET_NULL,
        related_name='erp_notifications_sent',
        null=True,
        blank=True,
    )
    template = models.ForeignKey(
        NotificationTemplate,
        verbose_name='Template',
        on_delete=models.SET_NULL,
        related_name='notifications',
        null=True,
        blank=True,
    )
    notification_type = models.CharField('Notification type', max_length=32, choices=NotificationTemplate.TYPE_CHOICES, default=NotificationTemplate.TYPE_SYSTEM, db_index=True)
    channel = models.CharField('Channel', max_length=32, choices=NotificationTemplate.CHANNEL_CHOICES, default=NotificationTemplate.CHANNEL_IN_APP, db_index=True)
    priority = models.CharField('Priority', max_length=32, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL, db_index=True)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True)
    title = models.CharField('Title', max_length=255)
    body = models.TextField('Body', blank=True)
    data = models.JSONField('Data', default=dict, blank=True)
    target_url = models.CharField('Target URL', max_length=500, blank=True)
    content_type = models.ForeignKey(ContentType, verbose_name='Related content type', on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveBigIntegerField('Related object id', null=True, blank=True, db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    queued_at = models.DateTimeField('Queued at', null=True, blank=True)
    sent_at = models.DateTimeField('Sent at', null=True, blank=True)
    read_at = models.DateTimeField('Read at', null=True, blank=True)
    failed_at = models.DateTimeField('Failed at', null=True, blank=True)
    error_message = models.TextField('Error message', blank=True)

    class Meta:
        verbose_name = 'ERP notification'
        verbose_name_plural = 'ERP notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['notification_type', 'status']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.recipient}: {self.title}'

    @property
    def is_read(self):
        return bool(self.read_at or self.status == self.STATUS_READ)

    def queue(self, save=True):
        self.status = self.STATUS_QUEUED
        self.queued_at = django_timezone.now()
        if save:
            self.save(update_fields=['status', 'queued_at', 'updated_at'])
        return self

    def mark_sent(self, save=True):
        self.status = self.STATUS_SENT
        self.sent_at = django_timezone.now()
        self.error_message = ''
        if save:
            self.save(update_fields=['status', 'sent_at', 'error_message', 'updated_at'])
        return self

    def mark_failed(self, error_message='', save=True):
        self.status = self.STATUS_FAILED
        self.failed_at = django_timezone.now()
        self.error_message = str(error_message or '')[:2000]
        if save:
            self.save(update_fields=['status', 'failed_at', 'error_message', 'updated_at'])
        return self

    def mark_read(self, save=True):
        self.status = self.STATUS_READ
        self.read_at = django_timezone.now()
        if save:
            self.save(update_fields=['status', 'read_at', 'updated_at'])
        return self


class NotificationLog(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    )

    notification = models.ForeignKey(Notification, verbose_name='Notification', on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    device_token = models.ForeignKey(DeviceToken, verbose_name='Device token', on_delete=models.SET_NULL, related_name='notification_logs', null=True, blank=True)
    channel = models.CharField('Channel', max_length=32, choices=NotificationTemplate.CHANNEL_CHOICES, db_index=True)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    provider = models.CharField('Provider', max_length=64, blank=True)
    recipient = models.CharField('Recipient', max_length=255, blank=True)
    request_data = models.JSONField('Request data', default=dict, blank=True)
    response_data = models.JSONField('Response data', default=dict, blank=True)
    error_message = models.TextField('Error message', blank=True)
    sent_at = models.DateTimeField('Sent at', null=True, blank=True)
    created_at = models.DateTimeField('Created at', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'ERP notification log'
        verbose_name_plural = 'ERP notification logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['notification', 'channel']),
            models.Index(fields=['device_token', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.channel} - {self.status}'
