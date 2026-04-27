from django.conf import settings
from django.db import models


class FCMDevice(models.Model):
    PLATFORM_CHOICES = (
        ('ios', 'iOS'),
        ('android', 'Android'),
        ('web', 'Web'),
        ('unknown', 'Unknown'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='fcm_devices',
        verbose_name='Пользователь',
    )
    token = models.TextField('Firebase token', unique=True)
    platform = models.CharField('Платформа', max_length=20, choices=PLATFORM_CHOICES, default='unknown')
    device_name = models.CharField('Название устройства', max_length=255, blank=True, default='')
    is_active = models.BooleanField('Активен', default=True)
    last_seen_at = models.DateTimeField('Последняя активность', auto_now=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)

    class Meta:
        verbose_name = 'Firebase устройство'
        verbose_name_plural = 'Firebase устройства'
        ordering = ['-last_seen_at']

    def __str__(self):
        return f'{self.user} — {self.platform}'