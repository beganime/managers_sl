import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.crm.models import Client
from apps.education.models import Program, University


class OnboardingSubmission(TimeStampedModel):
    STAGE_EXPRESS = 'express'
    STAGE_FULL = 'full'
    STAGE_CHOICES = (
        (STAGE_EXPRESS, 'Экспресс-заявка'),
        (STAGE_FULL, 'Полная анкета'),
    )
    KIND_APPLICANT = 'applicant'
    KIND_SCHOOL_STUDENT = 'school_student'
    KIND_CHOICES = (
        (KIND_APPLICANT, 'Абитуриент'),
        (KIND_SCHOOL_STUDENT, 'Школьник'),
    )

    STATUS_SUBMITTED = 'submitted'
    STATUS_IN_REVIEW = 'in_review'
    STATUS_CHANGES_REQUESTED = 'changes_requested'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_SUBMITTED, 'Отправлена'),
        (STATUS_IN_REVIEW, 'На проверке'),
        (STATUS_CHANGES_REQUESTED, 'Требуются исправления'),
        (STATUS_APPROVED, 'Одобрена'),
        (STATUS_REJECTED, 'Отклонена'),
    )

    public_id = models.UUIDField('Публичный ID', default=uuid.uuid4, unique=True, editable=False, db_index=True)
    access_token_hash = models.CharField('Хеш токена анкеты', max_length=64, editable=False)
    kind = models.CharField('Тип анкеты', max_length=24, choices=KIND_CHOICES)
    stage = models.CharField(
        'Этап заявки',
        max_length=16,
        choices=STAGE_CHOICES,
        default=STAGE_FULL,
        db_index=True,
    )
    academic_year = models.PositiveSmallIntegerField('Год поступления', db_index=True)
    status = models.CharField('Статус', max_length=24, choices=STATUS_CHOICES, default=STATUS_SUBMITTED, db_index=True)

    full_name = models.CharField('ФИО', max_length=255)
    phone = models.CharField('Телефон', max_length=80, db_index=True)
    email = models.EmailField('Email', blank=True)
    date_of_birth = models.DateField('Дата рождения', null=True, blank=True)
    citizenship = models.CharField('Гражданство', max_length=120, blank=True)
    payload = models.JSONField('Остальные данные анкеты', default=dict, blank=True)
    fcm_token = models.TextField('Firebase token', blank=True)

    review_comment = models.TextField('Комментарий менеджера', blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Проверил',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_onboarding_submissions',
    )
    reviewed_at = models.DateTimeField('Дата проверки', null=True, blank=True)
    submitted_at = models.DateTimeField('Дата отправки', default=timezone.now, db_index=True)
    client = models.OneToOneField(
        Client,
        verbose_name='Созданный клиент',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_submission',
    )

    class Meta:
        verbose_name = 'Анкета из приложения'
        verbose_name_plural = 'Анкеты из приложения'
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['status', 'submitted_at']),
            models.Index(fields=['academic_year', 'kind']),
        ]

    def __str__(self):
        return f'{self.full_name} — {self.get_status_display()}'

    @staticmethod
    def hash_access_token(raw_token):
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    @classmethod
    def issue_access_token(cls):
        raw_token = secrets.token_urlsafe(32)
        return raw_token, cls.hash_access_token(raw_token)

    def token_matches(self, raw_token):
        if not raw_token:
            return False
        return secrets.compare_digest(self.access_token_hash, self.hash_access_token(raw_token))


class OnboardingUniversityChoice(TimeStampedModel):
    submission = models.ForeignKey(
        OnboardingSubmission,
        verbose_name='Анкета',
        on_delete=models.CASCADE,
        related_name='university_choices',
    )
    university = models.ForeignKey(
        University,
        verbose_name='ВУЗ',
        on_delete=models.PROTECT,
        related_name='onboarding_choices',
    )
    programs = models.ManyToManyField(Program, verbose_name='Программы', related_name='onboarding_choices')
    rank = models.PositiveSmallIntegerField('Приоритет')

    class Meta:
        verbose_name = 'Выбор ВУЗа в анкете'
        verbose_name_plural = 'Выборы ВУЗов в анкетах'
        ordering = ['rank', 'id']
        constraints = [
            models.UniqueConstraint(fields=['submission', 'university'], name='uniq_onboarding_submission_university'),
            models.UniqueConstraint(fields=['submission', 'rank'], name='uniq_onboarding_submission_rank'),
        ]

    def __str__(self):
        return f'{self.submission.full_name}: {self.university}'


class AcademicYearSequence(models.Model):
    KIND_CHOICES = OnboardingSubmission.KIND_CHOICES

    academic_year = models.PositiveSmallIntegerField('Год')
    kind = models.CharField('Тип', max_length=24, choices=KIND_CHOICES)
    last_number = models.PositiveIntegerField('Последний номер', default=0)

    class Meta:
        verbose_name = 'Счётчик SL-ID'
        verbose_name_plural = 'Счётчики SL-ID'
        constraints = [
            models.UniqueConstraint(fields=['academic_year', 'kind'], name='uniq_sl_id_sequence_year_kind'),
        ]

    def __str__(self):
        return f'{self.academic_year}/{self.kind}: {self.last_number}'


class ClientServiceIdentity(TimeStampedModel):
    submission = models.OneToOneField(
        OnboardingSubmission,
        verbose_name='Анкета',
        on_delete=models.PROTECT,
        related_name='service_identity',
    )
    client = models.OneToOneField(
        Client,
        verbose_name='Клиент',
        on_delete=models.CASCADE,
        related_name='service_identity',
    )
    mobile_login = models.CharField('Логин Students Life', max_length=32, unique=True)
    shared_password = models.CharField('Единый пароль', max_length=128)
    tmmail_email = models.EmailField('Адрес TMmail', unique=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Учётные данные сервисов клиента'
        verbose_name_plural = 'Учётные данные сервисов клиентов'

    def __str__(self):
        return self.mobile_login


class ClientProvisioningStep(TimeStampedModel):
    STEP_MOBILE_ACCOUNT = 'mobile_account'
    STEP_TMMAIL = 'tmmail'
    STEP_CHOICES = (
        (STEP_MOBILE_ACCOUNT, 'Аккаунт Students Life'),
        (STEP_TMMAIL, 'Почтовый ящик TMmail'),
    )

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_DISABLED = 'disabled'
    STATUS_NOT_REQUIRED = 'not_required'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Ожидает запуска'),
        (STATUS_RUNNING, 'Выполняется'),
        (STATUS_SUCCESS, 'Готово'),
        (STATUS_FAILED, 'Ошибка'),
        (STATUS_DISABLED, 'Сервис не настроен'),
        (STATUS_NOT_REQUIRED, 'Не требуется'),
    )

    submission = models.ForeignKey(
        OnboardingSubmission,
        verbose_name='Анкета',
        on_delete=models.CASCADE,
        related_name='provisioning_steps',
    )
    client = models.ForeignKey(
        Client,
        verbose_name='Клиент',
        on_delete=models.CASCADE,
        related_name='provisioning_steps',
    )
    step = models.CharField('Шаг', max_length=32, choices=STEP_CHOICES)
    status = models.CharField('Статус', max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    event_id = models.CharField('Ключ идемпотентности', max_length=120, unique=True)
    attempt_count = models.PositiveIntegerField('Количество попыток', default=0)
    started_at = models.DateTimeField('Начало попытки', null=True, blank=True)
    finished_at = models.DateTimeField('Окончание попытки', null=True, blank=True)
    last_error = models.TextField('Последняя ошибка', blank=True)
    response_data = models.JSONField('Ответ сервиса', default=dict, blank=True)

    class Meta:
        verbose_name = 'Шаг подключения сервиса'
        verbose_name_plural = 'Шаги подключения сервисов'
        ordering = ['submission_id', 'step']
        constraints = [
            models.UniqueConstraint(
                fields=['submission', 'step'],
                name='uniq_client_provisioning_submission_step',
            ),
        ]
        indexes = [models.Index(fields=['status', 'updated_at'])]

    def __str__(self):
        return f'{self.client.sl_id}: {self.get_step_display()}'


class OnboardingReviewEvent(TimeStampedModel):
    DECISION_START_REVIEW = 'start_review'
    DECISION_APPROVE = 'approve'
    DECISION_REQUEST_CHANGES = 'request_changes'
    DECISION_REJECT = 'reject'
    DECISION_RESUBMIT = 'resubmit'
    DECISION_CHOICES = (
        (DECISION_START_REVIEW, 'Взята на проверку'),
        (DECISION_APPROVE, 'Одобрена'),
        (DECISION_REQUEST_CHANGES, 'Возвращена на исправление'),
        (DECISION_REJECT, 'Отклонена'),
        (DECISION_RESUBMIT, 'Повторно отправлена'),
    )

    submission = models.ForeignKey(
        OnboardingSubmission,
        verbose_name='Анкета',
        on_delete=models.CASCADE,
        related_name='review_events',
    )
    decision = models.CharField('Решение', max_length=32, choices=DECISION_CHOICES)
    from_status = models.CharField('Предыдущий статус', max_length=24)
    to_status = models.CharField('Новый статус', max_length=24)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Сотрудник',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='onboarding_review_events',
    )
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Событие проверки анкеты'
        verbose_name_plural = 'История проверки анкет'
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['submission', 'created_at'])]

    def __str__(self):
        return f'{self.submission_id}: {self.decision}'
