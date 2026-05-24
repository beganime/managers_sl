from django.conf import settings
from django.db import models

from apps.core.models import ActiveModel, TimeStampedModel
from apps.organizations.models import Company, Office


class CalendarEvent(TimeStampedModel, ActiveModel):
    VISIBILITY_PRIVATE = 'private'
    VISIBILITY_OFFICE = 'office'
    VISIBILITY_COMPANY = 'company'
    VISIBILITY_CHOICES = (
        (VISIBILITY_PRIVATE, 'Только мне'),
        (VISIBILITY_OFFICE, 'Офис'),
        (VISIBILITY_COMPANY, 'Вся компания'),
    )

    company = models.ForeignKey(Company, verbose_name='Компания', on_delete=models.CASCADE, related_name='portal_calendar_events')
    office = models.ForeignKey(Office, verbose_name='Офис', on_delete=models.SET_NULL, null=True, blank=True, related_name='portal_calendar_events')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Владелец события', on_delete=models.CASCADE, related_name='portal_calendar_events')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name='Участники', blank=True, related_name='portal_calendar_participations')
    title = models.CharField('Название', max_length=255, db_index=True)
    description = models.TextField('Описание', blank=True)
    event_date = models.DateField('Дата', db_index=True)
    start_time = models.TimeField('Время начала', null=True, blank=True)
    end_time = models.TimeField('Время окончания', null=True, blank=True)
    visibility = models.CharField('Видимость', max_length=32, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Кто создал',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portal_calendar_events_created',
    )

    class Meta:
        verbose_name = 'Событие календаря'
        verbose_name_plural = 'События календаря'
        ordering = ['event_date', 'start_time', 'title']
        indexes = [
            models.Index(fields=['company', 'office', 'event_date']),
            models.Index(fields=['owner', 'event_date']),
            models.Index(fields=['visibility', 'event_date']),
        ]

    def __str__(self):
        return f'{self.title} - {self.event_date}'
