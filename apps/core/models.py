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
