from django.db import models


class TimeStampedModel(models.Model):
    """Базовая модель с датами создания и обновления."""

    created_at = models.DateTimeField('Дата создания', auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True, db_index=True)

    class Meta:
        abstract = True


class ActiveModel(models.Model):
    """Базовая модель с флагом активности."""

    is_active = models.BooleanField('Активно', default=True, db_index=True)

    class Meta:
        abstract = True


class OrderedModel(models.Model):
    """Базовая модель для ручной сортировки."""

    sort_order = models.PositiveIntegerField('Порядок', default=0, db_index=True)

    class Meta:
        abstract = True


class SystemSetting(TimeStampedModel):
    key = models.CharField('Ключ', max_length=120, unique=True, db_index=True)
    value = models.TextField('Значение', blank=True)
    description = models.CharField('Описание', max_length=255, blank=True)

    class Meta:
        verbose_name = 'Системная настройка'
        verbose_name_plural = 'Системные настройки'
        ordering = ['key']

    def __str__(self):
        return self.key
