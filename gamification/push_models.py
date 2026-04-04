from django.conf import settings
from django.db import models


class DeviceToken(models.Model):
    PLATFORMS = (
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
        ('unknown', 'Unknown'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_tokens',
    )
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, choices=PLATFORMS, default='unknown')
    device_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'FCM токен устройства'
        verbose_name_plural = 'FCM токены устройств'
        ordering = ('-last_seen_at',)

    def __str__(self):
        return f'{self.user.email} / {self.platform}'


class PushBroadcast(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='push_broadcasts',
    )
    title = models.CharField(max_length=255)
    body = models.TextField()
    target_all = models.BooleanField(default=True)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Push-рассылка'
        verbose_name_plural = 'Push-рассылки'
        ordering = ('-created_at',)

    def __str__(self):
        return self.title