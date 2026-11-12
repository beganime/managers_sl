from django.conf import settings
from django.db import models

from apps.core.models import ActiveModel, TimeStampedModel
from apps.organizations.models import Company, Office


class ClientMotivationProfile(models.Model):
    TRACKS = [('medical', 'Медицина'), ('economics', 'Экономика и бизнес'), ('it', 'IT и программирование'),
              ('engineering', 'Инженерия'), ('humanities', 'Гуманитарные науки'), ('creative', 'Творчество и дизайн'),
              ('other', 'Другое')]
    client = models.OneToOneField('crm.Client', on_delete=models.CASCADE, related_name='motivation_profile')
    track = models.CharField('Основное направление', max_length=32, choices=TRACKS, blank=True, db_index=True)
    talents = models.TextField('Таланты и сильные стороны', max_length=1000, blank=True)
    hobbies = models.TextField('Хобби и любимые занятия', max_length=1000, blank=True)
    achievements = models.TextField('Достижения и опыт', max_length=1000, blank=True)
    motivation = models.TextField('Почему выбрал эту профессию?', max_length=1000, blank=True)
    goals = models.TextField('Какие планы после обучения?', max_length=1000, blank=True)
    next_question = models.CharField('Что важно уточнить при следующем разговоре?', max_length=255, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)


class ClientWorkspaceProfile(models.Model):
    client = models.OneToOneField('crm.Client', on_delete=models.CASCADE, related_name='workspace_profile')
    avatar = models.BinaryField(blank=True, default=bytes)
    password_encrypted = models.TextField(blank=True)
    account_status = models.CharField(max_length=32, blank=True)
    disk_root = models.CharField(max_length=1000, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class PortalPresence(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    seen_at = models.DateTimeField(auto_now=True)
    section = models.CharField(max_length=100)


class StaffSuggestion(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
    text = models.CharField(max_length=1000, blank=True)
    submitted_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'date'], name='unique_staff_suggestion_day')]


class MoodSupport(models.Model):
    mood = models.ForeignKey('EmployeeMood', on_delete=models.CASCADE, related_name='support')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    liked = models.BooleanField(default=False)
    comment = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['mood', 'user'], name='unique_mood_support_user')]


class EmployeeMood(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='daily_moods')
    date = models.DateField()
    slot = models.PositiveSmallIntegerField()
    score = models.PositiveSmallIntegerField(choices=((1, 'Тяжело'), (2, 'Не очень'), (3, 'Спокойно'), (4, 'Хорошо'), (5, 'Отлично')))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'slot']
        constraints = [
            models.UniqueConstraint(fields=['user', 'date', 'slot'], name='unique_employee_mood_slot'),
            models.CheckConstraint(condition=models.Q(slot__gte=1, slot__lte=3), name='employee_mood_three_slots'),
            models.CheckConstraint(condition=models.Q(score__gte=1, score__lte=5), name='employee_mood_score_range'),
        ]


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
