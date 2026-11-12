from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.crm.models import Client


class Payment(TimeStampedModel):
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'На проверке'),
        (STATUS_CONFIRMED, 'Подтверждена'),
        (STATUS_REJECTED, 'Отклонена'),
    )

    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Менеджер', on_delete=models.PROTECT, related_name='payments')
    client = models.ForeignKey(Client, verbose_name='Клиент', on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField('Сумма', max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    photo = models.FileField('Фото чека', upload_to='payments/%Y/%m/')
    note = models.CharField('Комментарий', max_length=500, blank=True)
    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Проверил',
        on_delete=models.SET_NULL,
        related_name='reviewed_payments',
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField('Проверено в', null=True, blank=True)
    review_note = models.CharField('Примечание проверки', max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Оплата'
        verbose_name_plural = 'Оплаты'
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return f'{self.manager} — {self.amount} ({self.get_status_display()})'


class PaymentRecipient(TimeStampedModel):
    """Администраторы, получающие Telegram-уведомления о новых оплатах."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name='Администратор',
        on_delete=models.CASCADE,
        related_name='payment_recipient',
    )

    class Meta:
        verbose_name = 'Получатель уведомлений об оплатах'
        verbose_name_plural = 'Получатели уведомлений об оплатах'

    def __str__(self):
        return str(self.user)
