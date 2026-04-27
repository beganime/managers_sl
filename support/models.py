from django.conf import settings
from django.db import models


class SupportMessage(models.Model):
    STATUS_CHOICES = (
        ('new', 'Новое'),
        ('in_progress', 'В работе'),
        ('closed', 'Закрыто'),
    )

    CATEGORY_CHOICES = (
        ('support', 'Поддержка'),
        ('feedback', 'Отзыв'),
        ('bug', 'Ошибка'),
        ('idea', 'Идея'),
        ('admin', 'Администратору'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='support_messages',
        verbose_name='Пользователь',
    )
    category = models.CharField('Категория', max_length=30, choices=CATEGORY_CHOICES, default='support')
    subject = models.CharField('Тема', max_length=255)
    message = models.TextField('Сообщение')
    status = models.CharField('Статус', max_length=30, choices=STATUS_CHOICES, default='new', db_index=True)
    admin_note = models.TextField('Заметка администратора', blank=True, default='')
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Обращение в поддержку'
        verbose_name_plural = 'Обращения в поддержку'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.subject} — {self.get_status_display()}'