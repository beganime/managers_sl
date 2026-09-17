import io
import os
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from apps.core.models import ActiveModel, TimeStampedModel
from apps.employees.models import EmployeeProfile
from apps.organizations.models import Company, Office


def client_questionnaire_document_upload_to(instance, filename):
    return f'erp/crm/client_questionnaires/{instance.client_id}/{uuid4().hex}-{filename}'


class LeadSource(TimeStampedModel, ActiveModel):
    name = models.CharField('Название источника', max_length=150, unique=True)
    code = models.SlugField('Код источника', max_length=80, unique=True)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'Источник лида'
        verbose_name_plural = 'Источники лидов'
        ordering = ['name']

    def __str__(self):
        return self.name


class Lead(TimeStampedModel):
    STATUS_CHOICES = (
        ('new', 'Новый'),
        ('contacted', 'Связались'),
        ('qualified', 'Квалифицирован'),
        ('converted', 'Стал клиентом'),
        ('lost', 'Потерян'),
        ('spam', 'Спам'),
    )

    DIRECTION_CHOICES = (
        ('admission', 'Поступление'),
        ('visa', 'Виза'),
        ('translation', 'Переводы'),
        ('tickets', 'Билеты'),
        ('work_visa', 'Рабочие визы'),
        ('other', 'Другое'),
    )

    company = models.ForeignKey(Company, verbose_name='Компания', on_delete=models.PROTECT, related_name='crm_leads')
    office = models.ForeignKey(Office, verbose_name='Офис', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_leads')
    source = models.ForeignKey(LeadSource, verbose_name='Источник', on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Ответственный менеджер', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_leads')

    full_name = models.CharField('ФИО / Имя', max_length=255)
    phone = models.CharField('Телефон', max_length=50, db_index=True)
    email = models.EmailField('Email', blank=True, null=True)
    country = models.CharField('Страна', max_length=100, blank=True)
    city = models.CharField('Город', max_length=100, blank=True)
    direction = models.CharField('Направление', max_length=50, choices=DIRECTION_CHOICES, blank=True)
    interested_country = models.CharField('Интересующая страна обучения', max_length=100, blank=True)
    interested_program = models.CharField('Интересующая программа', max_length=255, blank=True)
    status = models.CharField('Статус', max_length=32, choices=STATUS_CHOICES, default='new', db_index=True)
    comment = models.TextField('Комментарий', blank=True)
    custom_data = models.JSONField('Дополнительные данные', default=dict, blank=True)
    submitter_ip = models.GenericIPAddressField('IP отправителя', null=True, blank=True, db_index=True)
    submitter_user_agent = models.TextField('User-Agent', blank=True, default='')
    submitter_referer = models.URLField('Referer', max_length=1000, blank=True, default='')
    submitter_origin = models.URLField('Origin', max_length=1000, blank=True, default='')
    api_source = models.CharField('API source', max_length=100, blank=True, default='')
    taken_at = models.DateTimeField('Дата взятия ответственности', null=True, blank=True)
    converted_at = models.DateTimeField('Дата конвертации', null=True, blank=True)
    is_archived = models.BooleanField('В архиве', default=False, db_index=True)
    archived_at = models.DateTimeField('Дата архивации', null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Кто архивировал',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='archived_crm_leads',
    )
    archive_reason = models.TextField('Причина архивации', blank=True)

    class Meta:
        verbose_name = 'Лид'
        verbose_name_plural = 'Лиды'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['manager', 'status']),
            models.Index(fields=['is_archived', 'status']),
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        return f'{self.full_name} ({self.phone})'

    @property
    def action_history(self):
        history = (self.custom_data or {}).get('action_history', [])
        return history if isinstance(history, list) else []

    def log_action(self, action, user=None, note='', save=False):
        data = dict(self.custom_data or {})
        history = list(data.get('action_history') or [])
        history.append({
            'action': action,
            'at': timezone.now().isoformat(),
            'user_id': getattr(user, 'id', None),
            'user': user.get_full_name() or getattr(user, 'email', '') if user else '',
            'note': note or '',
        })
        data['action_history'] = history[-100:]
        self.custom_data = data
        if save:
            self.save(update_fields=['custom_data', 'updated_at'])

    def take_responsibility(self, user, company=None, office=None):
        self.manager = user
        if company is not None:
            self.company = company
        if office is not None:
            self.office = office
        self.status = 'contacted'
        if not self.taken_at:
            self.taken_at = timezone.now()
        self.log_action('take_responsibility', user)
        self.save(update_fields=['manager', 'company', 'office', 'status', 'taken_at', 'custom_data', 'updated_at'])

    def release_responsibility(self, user, note=''):
        self.manager = None
        self.status = 'new'
        self.taken_at = None
        self.log_action('release_responsibility', user, note=note)
        self.save(update_fields=['manager', 'status', 'taken_at', 'custom_data', 'updated_at'])

    def archive(self, user=None, reason=''):
        self.is_archived = True
        self.archived_at = timezone.now()
        self.archived_by = user
        self.archive_reason = reason or ''
        self.log_action('archive', user, note=reason)
        self.save(update_fields=['is_archived', 'archived_at', 'archived_by', 'archive_reason', 'custom_data', 'updated_at'])

    def restore_from_archive(self, user=None, note=''):
        self.is_archived = False
        self.archived_at = None
        self.archived_by = None
        self.archive_reason = ''
        self.log_action('restore', user, note=note)
        self.save(update_fields=['is_archived', 'archived_at', 'archived_by', 'archive_reason', 'custom_data', 'updated_at'])

    def mark_converted(self, user=None):
        self.status = 'converted'
        self.converted_at = timezone.now()
        self.log_action('convert_to_client', user)
        self.save(update_fields=['manager', 'company', 'office', 'status', 'converted_at', 'custom_data', 'updated_at'])


class Client(TimeStampedModel):
    # Nullable only during the explicit, reconciled identity backfill window.
    public_id = models.UUIDField(default=uuid4, unique=True, null=True, editable=False)
    FUNDING_CHOICES = (
        ('government', 'Государственная линия'),
        ('budget', 'Бюджет'),
        ('contract', 'Контракт'),
        ('medical', 'Медик'),
    )
    STATUS_CHOICES = (
        ('new', 'Новый'),
        ('consultation', 'Консультация'),
        ('documents', 'Сбор документов'),
        ('application', 'Подача заявки'),
        ('invitation', 'Приглашение'),
        ('visa', 'Виза'),
        ('arrived', 'Прибыл'),
        ('success', 'Завершён успешно'),
        ('rejected', 'Отказ'),
        ('archive', 'Архив'),
    )

    company = models.ForeignKey(Company, verbose_name='Компания', on_delete=models.PROTECT, related_name='crm_clients')
    office = models.ForeignKey(Office, verbose_name='Офис', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_clients')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Основной менеджер', on_delete=models.PROTECT, related_name='crm_clients')
    shared_with = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='shared_crm_clients', verbose_name='Доступ открыт также для')
    is_public = models.BooleanField('Доступен сотрудникам компании', default=False, db_index=True)
    source_lead = models.OneToOneField(Lead, verbose_name='Исходный лид', on_delete=models.SET_NULL, null=True, blank=True, related_name='client')
    lead_source = models.ForeignKey(LeadSource, verbose_name='Источник', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_clients')
    direction = models.CharField('Направление', max_length=50, choices=Lead.DIRECTION_CHOICES, blank=True)

    full_name = models.CharField('ФИО клиента', max_length=255, db_index=True)
    phone = models.CharField('Телефон', max_length=50, db_index=True)
    email = models.EmailField('Email', blank=True, null=True)
    dob = models.DateField('Дата рождения', null=True, blank=True)
    citizenship = models.CharField('Гражданство', max_length=100, blank=True)
    city = models.CharField('Город', max_length=100, blank=True)
    address = models.TextField('Адрес проживания', blank=True)
    address_registration = models.TextField('Адрес регистрации', blank=True)
    passport_local_num = models.CharField('Внутренний паспорт', max_length=50, blank=True)
    passport_inter_num = models.CharField('Загранпаспорт', max_length=50, blank=True)
    passport_issued_by = models.CharField('Кем выдан паспорт', max_length=255, blank=True)
    passport_issued_date = models.DateField('Дата выдачи паспорта', null=True, blank=True)
    passport_valid_until = models.DateField('Срок действия паспорта', null=True, blank=True)
    passport_birth_place = models.CharField('Место рождения', max_length=255, blank=True)
    relative_full_name = models.CharField('ФИО родственника', max_length=255, blank=True)
    relative_relation = models.CharField('Кем приходится', max_length=120, blank=True)
    relative_phone = models.CharField('Телефон родственника', max_length=80, blank=True)
    relative_workplace = models.CharField('Место работы родственника', max_length=255, blank=True)
    current_education = models.CharField('Текущее образование', max_length=255, blank=True)
    current_school = models.CharField('Текущий вуз / школа', max_length=255, blank=True)
    current_study_country = models.CharField('Страна текущего обучения', max_length=100, blank=True)
    interested_country = models.CharField('Интересующая страна', max_length=100, blank=True)
    interested_university = models.CharField('Интересующий вуз', max_length=255, blank=True)
    interested_program = models.CharField('Интересующая программа', max_length=255, blank=True)
    has_passport = models.BooleanField('Есть паспорт', default=False)
    has_education_doc = models.BooleanField('Есть аттестат / диплом', default=False)
    has_translation = models.BooleanField('Есть перевод', default=False)
    has_photo = models.BooleanField('Есть фото', default=False)
    status = models.CharField('Статус', max_length=32, choices=STATUS_CHOICES, default='new', db_index=True)
    is_priority = models.BooleanField('Приоритетный клиент', default=False)
    is_partner_client = models.BooleanField('Клиент от партнёра', default=False)
    partner_name = models.CharField('Партнёр', max_length=255, blank=True)
    comments = models.TextField('Комментарии', blank=True)
    custom_data = models.JSONField('Дополнительные данные', default=dict, blank=True)
    sl_id = models.CharField('SL-ID', max_length=32, unique=True, null=True, blank=True, db_index=True)
    academic_year = models.PositiveSmallIntegerField('Год поступления', null=True, blank=True, db_index=True)
    funding_type = models.CharField('Форма поступления', max_length=20, choices=FUNDING_CHOICES, blank=True)

    class Meta:
        verbose_name = 'Клиент CRM'
        verbose_name_plural = 'Клиенты CRM'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['manager', 'status']),
            models.Index(fields=['phone']),
            models.Index(fields=['full_name']),
        ]

    def __str__(self):
        return f'{self.full_name} [{self.get_status_display()}]'


    mobile_app_user_id = models.PositiveIntegerField('Mobile app user ID', null=True, blank=True, db_index=True)
    mobile_app_source = models.BooleanField('Mobile app client', default=False)


class Application(TimeStampedModel):
    STAGE_LEAD = 'LEAD'
    STAGE_CLIENT_CREATED = 'CLIENT_CREATED'
    STAGE_DOCUMENT_COLLECTION = 'DOCUMENT_COLLECTION'
    STAGE_DOCUMENTS_READY = 'DOCUMENTS_READY'
    STAGE_APPLICATION_PREPARATION = 'APPLICATION_PREPARATION'
    STAGE_APPLICATION_SUBMITTED = 'APPLICATION_SUBMITTED'
    STAGE_UNIVERSITY_REVIEW = 'UNIVERSITY_REVIEW'
    STAGE_EXAM_REQUIRED = 'EXAM_REQUIRED'
    STAGE_EXAM_SCHEDULED = 'EXAM_SCHEDULED'
    STAGE_EXAM_COMPLETED = 'EXAM_COMPLETED'
    STAGE_WAITING_RESULT = 'WAITING_RESULT'
    STAGE_EXAM_PASSED = 'EXAM_PASSED'
    STAGE_EXAM_FAILED = 'EXAM_FAILED'
    STAGE_CONTRACT_WAITING = 'CONTRACT_WAITING'
    STAGE_CONTRACT_RECEIVED = 'CONTRACT_RECEIVED'
    STAGE_UNIVERSITY_PAYMENT_WAITING = 'UNIVERSITY_PAYMENT_WAITING'
    STAGE_UNIVERSITY_PAYMENT_CONFIRMED = 'UNIVERSITY_PAYMENT_CONFIRMED'
    STAGE_ADMISSION_CONFIRMED = 'ADMISSION_CONFIRMED'
    STAGE_ORDER_WAITING = 'ORDER_WAITING'
    STAGE_INVITATION_WAITING = 'INVITATION_WAITING'
    STAGE_INVITATION_RECEIVED = 'INVITATION_RECEIVED'
    STAGE_VISA_PREPARATION = 'VISA_PREPARATION'
    STAGE_VISA_APPLIED = 'VISA_APPLIED'
    STAGE_VISA_RECEIVED = 'VISA_RECEIVED'
    STAGE_ARRIVAL_PLANNED = 'ARRIVAL_PLANNED'
    STAGE_ENROLLED = 'ENROLLED'
    STAGE_REJECTED = 'REJECTED'
    STAGE_CANCELLED = 'CANCELLED'
    STAGE_ON_HOLD = 'ON_HOLD'
    STAGE_CHOICES = tuple((value, label) for value, label in (
        (STAGE_LEAD, 'Лид'), (STAGE_CLIENT_CREATED, 'Клиент создан'),
        (STAGE_DOCUMENT_COLLECTION, 'Сбор документов'), (STAGE_DOCUMENTS_READY, 'Документы готовы'),
        (STAGE_APPLICATION_PREPARATION, 'Подготовка заявки'), (STAGE_APPLICATION_SUBMITTED, 'Заявка подана'),
        (STAGE_UNIVERSITY_REVIEW, 'Рассмотрение вузом'), (STAGE_EXAM_REQUIRED, 'Требуется экзамен'),
        (STAGE_EXAM_SCHEDULED, 'Экзамен назначен'), (STAGE_EXAM_COMPLETED, 'Экзамен пройден'),
        (STAGE_WAITING_RESULT, 'Ожидание результата'), (STAGE_EXAM_PASSED, 'Экзамен сдан'),
        (STAGE_EXAM_FAILED, 'Экзамен не сдан'), (STAGE_CONTRACT_WAITING, 'Ожидание договора вуза'),
        (STAGE_CONTRACT_RECEIVED, 'Договор вуза получен'),
        (STAGE_UNIVERSITY_PAYMENT_WAITING, 'Ожидание оплаты вузу'),
        (STAGE_UNIVERSITY_PAYMENT_CONFIRMED, 'Оплата вузу подтверждена'),
        (STAGE_ADMISSION_CONFIRMED, 'Поступление подтверждено'), (STAGE_ORDER_WAITING, 'Ожидание приказа'),
        (STAGE_INVITATION_WAITING, 'Ожидание приглашения'), (STAGE_INVITATION_RECEIVED, 'Приглашение получено'),
        (STAGE_VISA_PREPARATION, 'Подготовка визы'), (STAGE_VISA_APPLIED, 'Документы на визу поданы'),
        (STAGE_VISA_RECEIVED, 'Виза получена'), (STAGE_ARRIVAL_PLANNED, 'Прибытие запланировано'),
        (STAGE_ENROLLED, 'Зачислен'), (STAGE_REJECTED, 'Отказ'),
        (STAGE_CANCELLED, 'Отменено'), (STAGE_ON_HOLD, 'Приостановлено'),
    ))
    public_id = models.UUIDField(default=uuid4, unique=True, null=True, editable=False)
    university = models.ForeignKey('education.University', on_delete=models.PROTECT, null=True, blank=True, related_name='crm_applications')
    program = models.ForeignKey('education.Program', on_delete=models.PROTECT, null=True, blank=True, related_name='crm_applications')
    # Keep `country` as legacy text until all existing API consumers migrate.
    country_reference = models.ForeignKey('education.Country', on_delete=models.PROTECT, null=True, blank=True, related_name='crm_applications')
    academic_year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    STATUS_CHOICES = (
        ('draft', 'Черновик'),
        ('documents', 'Сбор документов'),
        ('submitted', 'Подано'),
        ('in_review', 'На рассмотрении'),
        ('accepted', 'Принято'),
        ('invitation', 'Приглашение получено'),
        ('visa', 'Виза'),
        ('enrolled', 'Зачислен'),
        ('rejected', 'Отказ'),
        ('cancelled', 'Отменено'),
    )

    client = models.ForeignKey(Client, verbose_name='Клиент', on_delete=models.CASCADE, related_name='applications')
    company = models.ForeignKey(Company, verbose_name='Компания', on_delete=models.PROTECT, related_name='crm_applications')
    office = models.ForeignKey(Office, verbose_name='Офис', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_applications')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Ответственный', on_delete=models.PROTECT, related_name='crm_applications')

    university_name = models.CharField('ВУЗ', max_length=255, blank=True)
    program_name = models.CharField('Программа', max_length=255, blank=True)
    country = models.CharField('Страна обучения', max_length=100, blank=True)
    degree = models.CharField('Степень', max_length=100, blank=True)
    language = models.CharField('Язык обучения', max_length=100, blank=True)
    intake = models.CharField('Набор / intake', max_length=100, blank=True)
    status = models.CharField('Статус заявки', max_length=32, choices=STATUS_CHOICES, default='draft', db_index=True)
    current_stage = models.CharField(
        'Этап поступления', max_length=40, choices=STAGE_CHOICES,
        default=STAGE_DOCUMENT_COLLECTION, db_index=True,
    )
    funding_type = models.CharField('Форма поступления', max_length=20, choices=Client.FUNDING_CHOICES, blank=True)
    deadline = models.DateTimeField('Дедлайн', null=True, blank=True, db_index=True)
    admission_result = models.CharField('Результат поступления', max_length=80, blank=True)
    submitted_at = models.DateField('Дата подачи', null=True, blank=True)
    decision_at = models.DateField('Дата решения', null=True, blank=True)
    comment = models.TextField('Комментарий', blank=True)
    custom_data = models.JSONField('Дополнительные данные', default=dict, blank=True)

    class Meta:
        verbose_name = 'Заявка на поступление'
        verbose_name_plural = 'Заявки на поступление'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['manager', 'status']),
            models.Index(fields=['client', 'status']),
        ]

    def __str__(self):
        return f'{self.client.full_name} — {self.university_name or "ВУЗ не выбран"}'


class ApplicationStageHistory(TimeStampedModel):
    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name='stage_history')
    old_stage = models.CharField(max_length=40, choices=Application.STAGE_CHOICES, blank=True)
    new_stage = models.CharField(max_length=40, choices=Application.STAGE_CHOICES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='application_stage_events',
    )
    source_service = models.CharField(max_length=80, default='manager_sl')
    comment = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ['-created_at']
        default_permissions = ('add', 'view')
        indexes = [models.Index(fields=['application', 'created_at'])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('История этапов не изменяется после создания.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('История этапов не удаляется.')


class ActivityLog(TimeStampedModel):
    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='canonical_activity_events',
    )
    service = models.CharField(max_length=80, default='manager_sl', db_index=True)
    student = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='canonical_activity')
    application = models.ForeignKey(
        Application, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='canonical_activity',
    )
    object_type = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    old_data = models.JSONField(default=dict, blank=True)
    new_data = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        default_permissions = ('add', 'view')
        indexes = [
            models.Index(fields=['student', 'created_at']),
            models.Index(fields=['application', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Журнал действий не изменяется после создания.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Журнал действий не удаляется.')


class ApplicationExam(TimeStampedModel):
    """Canonical exam record belonging to one university application."""

    STATUS_SCHEDULED = 'SCHEDULED'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_PASSED = 'PASSED'
    STATUS_FAILED = 'FAILED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = (
        (STATUS_SCHEDULED, 'Назначен'),
        (STATUS_CONFIRMED, 'Подтверждён'),
        (STATUS_COMPLETED, 'Пройден'),
        (STATUS_PASSED, 'Сдан'),
        (STATUS_FAILED, 'Не сдан'),
        (STATUS_CANCELLED, 'Отменён'),
    )

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name='exams', verbose_name='Заявка в университет',
    )
    student = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name='application_exams', verbose_name='Студент',
    )
    subject = models.CharField('Экзамен / предмет', max_length=255)
    scheduled_at = models.DateTimeField('Дата и время', db_index=True)
    timezone = models.CharField('Часовой пояс', max_length=64, default='Asia/Ashgabat')
    join_url = models.URLField('Ссылка', max_length=1000, blank=True)
    login = models.CharField('Логин', max_length=255, blank=True)
    secret_ciphertext = models.TextField('Зашифрованный пароль', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED, db_index=True)
    result = models.CharField('Результат', max_length=255, blank=True)
    score = models.CharField('Балл', max_length=80, blank=True)
    retake_at = models.DateTimeField('Пересдача', null=True, blank=True)
    comment = models.CharField('Комментарий', max_length=1000, blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='responsible_application_exams', verbose_name='Ответственный',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_application_exams', verbose_name='Создал',
    )
    source_service = models.CharField(max_length=80, default='manager_sl')
    source_id = models.CharField(max_length=120)
    source_version = models.PositiveIntegerField(default=1)
    client_acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['scheduled_at', 'created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source_service', 'source_id'], name='unique_exam_source_record',
            ),
        ]
        indexes = [
            models.Index(fields=['application', 'scheduled_at']),
            models.Index(fields=['student', 'scheduled_at']),
            models.Index(fields=['status', 'scheduled_at']),
        ]

    @property
    def has_secret(self):
        return bool(self.secret_ciphertext)

    def clean(self):
        super().clean()
        if self.application_id and self.student_id and self.application.client_id != self.student_id:
            raise ValidationError({'application': 'Заявка должна принадлежать выбранному студенту.'})

    def __str__(self):
        return f'{self.student.full_name} — {self.subject}'


class ApplicationExamEvent(TimeStampedModel):
    """Append-only, idempotent history of exam changes across services."""

    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    exam = models.ForeignKey(ApplicationExam, on_delete=models.PROTECT, related_name='events')
    action = models.CharField(max_length=80, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='application_exam_events',
    )
    source_service = models.CharField(max_length=80, default='manager_sl')
    old_data = models.JSONField(default=dict, blank=True)
    new_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        default_permissions = ('add', 'view')
        indexes = [models.Index(fields=['exam', 'created_at'])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('История экзамена не изменяется после создания.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('История экзамена не удаляется.')


class TranslationRecord(TimeStampedModel):
    """Canonical translation linked to a student and, where possible, a document version."""

    STATUS_UPLOADED = 'UPLOADED'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_REVIEW = 'REVIEW'
    STATUS_READY = 'READY'
    STATUS_ERROR = 'ERROR'
    STATUS_CHOICES = (
        (STATUS_UPLOADED, 'Загружен'),
        (STATUS_PROCESSING, 'Обрабатывается'),
        (STATUS_REVIEW, 'На проверке'),
        (STATUS_READY, 'Готов'),
        (STATUS_ERROR, 'Ошибка'),
    )

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    student = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name='translations', null=True, blank=True,
        verbose_name='Студент',
    )
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name='translations', null=True, blank=True,
        verbose_name='Заявка в университет',
    )
    source_document_version = models.ForeignKey(
        'ClientFileVersion', on_delete=models.PROTECT, related_name='translations', null=True, blank=True,
        verbose_name='Исходная версия документа',
    )
    title = models.CharField('Название', max_length=255)
    source_language = models.CharField('Исходный язык', max_length=16, default='tk')
    target_language = models.CharField('Язык перевода', max_length=16, default='ru')
    template_name = models.CharField('Шаблон', max_length=255, blank=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPLOADED, db_index=True)
    source_storage_path = models.CharField(max_length=1000, blank=True)
    result_storage_path = models.CharField(max_length=1000, blank=True)
    translator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='translated_documents',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_translations',
    )
    source_service = models.CharField(max_length=80, default='translate_sl')
    source_id = models.CharField(max_length=120)
    source_version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source_service', 'source_id'], name='unique_translation_source_record',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['application', 'created_at']),
        ]

    def clean(self):
        super().clean()
        if self.application_id and self.student_id and self.application.client_id != self.student_id:
            raise ValidationError({'application': 'Заявка должна принадлежать выбранному студенту.'})
        if self.source_document_version_id:
            version = self.source_document_version
            if self.student_id and version.document.client_id != self.student_id:
                raise ValidationError({'source_document_version': 'Документ принадлежит другому студенту.'})

    def __str__(self):
        owner = self.student.full_name if self.student_id else 'Не привязан к клиенту'
        return f'{owner} — {self.title}'


class TranslationEvent(TimeStampedModel):
    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    translation = models.ForeignKey(TranslationRecord, on_delete=models.PROTECT, related_name='events')
    action = models.CharField(max_length=80, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='translation_events',
    )
    source_service = models.CharField(max_length=80, default='translate_sl')
    old_data = models.JSONField(default=dict, blank=True)
    new_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        default_permissions = ('add', 'view')
        indexes = [models.Index(fields=['translation', 'created_at'])]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('История перевода не изменяется после создания.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('История перевода не удаляется.')


class EmailRecord(TimeStampedModel):
    """Canonical mail metadata linked to a student without copying mailbox content."""

    CATEGORY_CHOICES = (
        ('primary', 'Основные'),
        ('google', 'Уведомления Google'),
        ('spam', 'Спам'),
        ('sent', 'Отправленные'),
    )
    IMPORTANCE_CHOICES = (
        ('normal', 'Обычное'),
        ('important', 'Важное'),
        ('urgent', 'Срочное'),
    )

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    student = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name='email_records', null=True, blank=True,
        verbose_name='Студент',
    )
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name='email_records', null=True, blank=True,
        verbose_name='Заявка в университет',
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='responsible_email_records',
        null=True, blank=True, verbose_name='Ответственный',
    )
    source_service = models.CharField(max_length=80, default='smtp_sl')
    source_id = models.CharField(max_length=160)
    mailbox = models.EmailField('Почтовый ящик')
    sender_email = models.EmailField('Отправитель')
    sender_name = models.CharField('Имя отправителя', max_length=255, blank=True)
    recipient_email = models.EmailField('Получатель')
    subject = models.CharField('Тема', max_length=500, blank=True)
    received_at = models.DateTimeField('Получено', db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='primary', db_index=True)
    importance = models.CharField(max_length=20, choices=IMPORTANCE_CHOICES, default='normal', db_index=True)
    university_name = models.CharField('Вуз', max_length=255, blank=True, db_index=True)
    attachment_count = models.PositiveSmallIntegerField(default=0)
    body_preview = models.CharField('Фрагмент письма', max_length=1000, blank=True)
    source_url = models.URLField('Открыть в почтовом сервисе', max_length=1000, blank=True)
    is_read = models.BooleanField('Прочитано', default=False)
    is_replied = models.BooleanField('Ответ отправлен', default=False)
    processed = models.BooleanField('Обработано', default=False, db_index=True)
    source_version = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'Письмо студента'
        verbose_name_plural = 'Письма студентов'
        ordering = ['-received_at', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source_service', 'source_id'], name='unique_email_source_record',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'received_at']),
            models.Index(fields=['application', 'received_at']),
            models.Index(fields=['responsible', 'processed', 'received_at']),
        ]

    def clean(self):
        super().clean()
        if self.application_id and self.student_id and self.application.client_id != self.student_id:
            raise ValidationError({'application': 'Заявка должна принадлежать выбранному студенту.'})

    def __str__(self):
        return f'{self.subject or "Без темы"} — {self.mailbox}'


class ExternalAccount(TimeStampedModel):
    SYSTEM_RUID = 'RUID'
    SYSTEM_UNIVERSITY = 'UNIVERSITY_PORTAL'
    SYSTEM_GOVERNMENT = 'GOVERNMENT_PORTAL'
    SYSTEM_EMAIL = 'EMAIL'
    SYSTEM_OTHER = 'OTHER'
    SYSTEM_CHOICES = (
        (SYSTEM_RUID, 'RUID'),
        (SYSTEM_UNIVERSITY, 'Личный кабинет университета'),
        (SYSTEM_GOVERNMENT, 'Государственный портал'),
        (SYSTEM_EMAIL, 'Почтовый аккаунт'),
        (SYSTEM_OTHER, 'Другая система'),
    )

    STATUS_PLANNED = 'PLANNED'
    STATUS_CREATED = 'CREATED'
    STATUS_PENDING = 'PENDING_VERIFICATION'
    STATUS_VERIFIED = 'VERIFIED'
    STATUS_BLOCKED = 'BLOCKED'
    STATUS_ERROR = 'ERROR'
    STATUS_ARCHIVED = 'ARCHIVED'
    STATUS_CHOICES = (
        (STATUS_PLANNED, 'Нужно создать'),
        (STATUS_CREATED, 'Создан'),
        (STATUS_PENDING, 'Ожидает подтверждения'),
        (STATUS_VERIFIED, 'Подтверждён'),
        (STATUS_BLOCKED, 'Заблокирован'),
        (STATUS_ERROR, 'Проблема'),
        (STATUS_ARCHIVED, 'Архив'),
    )

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    student = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name='external_accounts', verbose_name='Студент',
    )
    application = models.ForeignKey(
        Application, on_delete=models.PROTECT, related_name='external_accounts',
        null=True, blank=True, verbose_name='Заявка в университет',
    )
    system = models.CharField('Система', max_length=40, choices=SYSTEM_CHOICES, db_index=True)
    provider_name = models.CharField('Название портала / вуза', max_length=255)
    portal_url = models.URLField('Адрес входа', blank=True)
    email = models.EmailField('Email аккаунта', blank=True)
    login = models.CharField('Логин', max_length=255, blank=True)
    secret_ciphertext = models.TextField('Зашифрованные данные доступа', blank=True, editable=False)
    secret_updated_at = models.DateTimeField('Пароль обновлён', null=True, blank=True, editable=False)
    status = models.CharField('Статус', max_length=32, choices=STATUS_CHOICES, default=STATUS_PLANNED, db_index=True)
    last_checked_at = models.DateTimeField('Последняя проверка', null=True, blank=True)
    issue = models.CharField('Проблема', max_length=1000, blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='responsible_external_accounts',
        verbose_name='Ответственный',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='created_external_accounts',
        null=True, blank=True, verbose_name='Кто создал запись',
    )
    notes = models.CharField('Комментарий', max_length=1000, blank=True)

    class Meta:
        verbose_name = 'Внешний аккаунт студента'
        verbose_name_plural = 'Внешние аккаунты студентов'
        ordering = ['-created_at']
        permissions = [('view_externalaccount_secret', 'Может просматривать пароль внешнего аккаунта')]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'application', 'system', 'provider_name'],
                name='crm_unique_external_account',
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['application', 'status']),
            models.Index(fields=['system', 'status']),
        ]

    @property
    def has_secret(self):
        return bool(self.secret_ciphertext)

    def clean(self):
        super().clean()
        if self.application_id and self.application.client_id != self.student_id:
            raise ValidationError({'application': 'Заявка должна принадлежать выбранному студенту.'})

    def __str__(self):
        return f'{self.get_system_display()}: {self.provider_name} — {self.student.full_name}'


class ClientActivity(TimeStampedModel):
    ACTIVITY_TYPE_CHOICES = (
        ('call', 'Звонок'),
        ('message', 'Сообщение'),
        ('meeting', 'Встреча'),
        ('note', 'Заметка'),
        ('status_change', 'Смена статуса'),
        ('document', 'Документ'),
        ('payment', 'Платёж'),
    )

    client = models.ForeignKey(Client, verbose_name='Клиент', on_delete=models.CASCADE, related_name='activities')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Менеджер', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_activities')
    activity_type = models.CharField('Тип активности', max_length=32, choices=ACTIVITY_TYPE_CHOICES, default='note')
    title = models.CharField('Заголовок', max_length=255)
    description = models.TextField('Описание', blank=True)
    due_at = models.DateTimeField('Срок / напоминание', null=True, blank=True)
    completed_at = models.DateTimeField('Выполнено', null=True, blank=True)

    class Meta:
        verbose_name = 'Активность клиента'
        verbose_name_plural = 'Активности клиентов'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_activity_type_display()}: {self.client.full_name}'


class ClientNote(TimeStampedModel):
    client = models.ForeignKey(Client, verbose_name='Клиент', on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Автор', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_notes')
    text = models.TextField('Текст заметки')
    is_private = models.BooleanField('Приватная заметка', default=False)

    class Meta:
        verbose_name = 'Заметка клиента'
        verbose_name_plural = 'Заметки клиентов'
        ordering = ['-created_at']

    def __str__(self):
        return f'Заметка: {self.client.full_name}'


class ClientFile(TimeStampedModel):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    client = models.ForeignKey(Client, verbose_name='Клиент', on_delete=models.CASCADE, related_name='files')
    application = models.ForeignKey(Application, verbose_name='Заявка', on_delete=models.CASCADE, null=True, blank=True, related_name='files')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Кто загрузил', on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_files')
    title = models.CharField('Название файла', max_length=255)
    file = models.FileField('Файл', upload_to='erp/crm/client_files/')
    file_type = models.CharField('Тип файла', max_length=100, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Файл клиента'
        verbose_name_plural = 'Файлы клиентов'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'external_mobile_document_id'],
                condition=models.Q(external_mobile_document_id__isnull=False),
                name='unique_external_mobile_document_per_source',
            ),
        ]

    def __str__(self):
        return self.title

    external_file_url = models.URLField('External file URL', max_length=1000, blank=True)
    external_mobile_document_id = models.PositiveIntegerField('Mobile document ID', null=True, blank=True, db_index=True)
    external_mobile_user_id = models.PositiveIntegerField('Mobile user ID', null=True, blank=True, db_index=True)
    source = models.CharField('Source', max_length=80, blank=True)
    has_translation = models.BooleanField('Has translation', default=False)
    status = models.CharField('Review status', max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    review_comment = models.TextField('Review comment', blank=True)
    reviewed_at = models.DateTimeField('Reviewed at', null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Reviewed by', on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_crm_files')
    external_review_data = models.JSONField('Ответ проверки Student’s Life', default=dict, blank=True)
    current_version_number = models.PositiveIntegerField('Текущая версия', default=0, editable=False)

    @property
    def external_reviewed_by_name(self):
        data = self.external_review_data or {}
        return data.get('reviewed_by_name') or ''

    @property
    def external_reviewed_by_email(self):
        data = self.external_review_data or {}
        return data.get('reviewed_by_email') or ''

    @property
    def reviewed_by_display(self):
        data = self.external_review_data or {}
        external_display = data.get('reviewed_by_display') or data.get('reviewed_by_name') or data.get('reviewed_by_email')
        if external_display:
            return external_display
        if self.reviewed_by_id:
            return self.reviewed_by.get_full_name() or self.reviewed_by.email
        return ''


class ClientFileVersion(TimeStampedModel):
    """Immutable metadata for one physical upload stored in DiskSL."""

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    document = models.ForeignKey(ClientFile, on_delete=models.CASCADE, related_name='versions')
    application = models.ForeignKey(
        Application, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='document_versions',
    )
    version_number = models.PositiveIntegerField()
    original_name = models.CharField(max_length=255)
    storage_path = models.CharField(max_length=1000)
    folder_url = models.URLField(max_length=1000, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    source_service = models.CharField(max_length=80, default='manager_sl', db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_client_file_versions',
    )
    uploader_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-version_number']
        default_permissions = ('add', 'view')
        constraints = [
            models.UniqueConstraint(fields=['document', 'version_number'], name='unique_client_file_version'),
        ]
        indexes = [
            models.Index(fields=['document', 'version_number']),
            models.Index(fields=['application', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Версия файла не изменяется после загрузки.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Версия файла не удаляется отдельно от документа.')


class ClientFileReviewEvent(TimeStampedModel):
    """Append-only decision for a specific physical document version."""

    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    document = models.ForeignKey(ClientFile, on_delete=models.CASCADE, related_name='review_events')
    version = models.ForeignKey(ClientFileVersion, on_delete=models.CASCADE, related_name='review_events')
    status = models.CharField(max_length=20, choices=ClientFile.STATUS_CHOICES)
    comment = models.CharField(max_length=1000, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='client_file_review_events',
    )
    reviewer_data = models.JSONField(default=dict, blank=True)
    source_service = models.CharField(max_length=80, default='manager_sl', db_index=True)

    class Meta:
        ordering = ['-created_at']
        default_permissions = ('add', 'view')
        indexes = [
            models.Index(fields=['document', 'created_at']),
            models.Index(fields=['version', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('История проверки документа не изменяется.')
        if self.version_id and self.document_id and self.version.document_id != self.document_id:
            raise ValidationError('Версия должна принадлежать выбранному документу.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('История проверки документа не удаляется.')


class ManagerDocumentPlan(TimeStampedModel, ActiveModel):
    PERIOD_DAY = 'day'
    PERIOD_WEEK = 'week'
    PERIOD_MONTH = 'month'
    PERIOD_CUSTOM = 'custom'
    PERIOD_CHOICES = (
        (PERIOD_DAY, 'День'),
        (PERIOD_WEEK, 'Неделя'),
        (PERIOD_MONTH, 'Месяц'),
        (PERIOD_CUSTOM, 'Произвольный период'),
    )

    employee = models.ForeignKey(EmployeeProfile, verbose_name='Менеджер', on_delete=models.CASCADE, related_name='document_plans')
    period_type = models.CharField('Период', max_length=16, choices=PERIOD_CHOICES, default=PERIOD_MONTH)
    start_date = models.DateField('Дата начала', db_index=True)
    end_date = models.DateField('Дата окончания', db_index=True)
    target_clients = models.PositiveIntegerField('План по загруженным клиентам', default=0)
    admin_comment = models.TextField('Комментарий администратора', blank=True)

    class Meta:
        verbose_name = 'План менеджера по документам'
        verbose_name_plural = 'Планы менеджеров по документам'
        ordering = ['-start_date', 'employee__user__first_name']
        indexes = [
            models.Index(fields=['employee', 'start_date', 'end_date', 'is_active'], name='crm_mdocplan_emp_period_idx'),
        ]

    def __str__(self):
        return f'{self.employee} — {self.start_date:%d.%m.%Y}-{self.end_date:%d.%m.%Y}'


class ManagerDocumentCredit(TimeStampedModel):
    EVENT_UPLOADED_CLIENT_DOCUMENTS = 'uploaded_client_documents'
    EVENT_CHOICES = (
        (EVENT_UPLOADED_CLIENT_DOCUMENTS, 'Документы клиента загружены'),
    )

    employee = models.ForeignKey(EmployeeProfile, verbose_name='Менеджер', on_delete=models.CASCADE, related_name='document_credits')
    client = models.ForeignKey(Client, verbose_name='Клиент', on_delete=models.CASCADE, related_name='document_manager_credits')
    plan = models.ForeignKey(ManagerDocumentPlan, verbose_name='План', on_delete=models.SET_NULL, null=True, blank=True, related_name='credits')
    event_type = models.CharField('Тип события', max_length=64, choices=EVENT_CHOICES, default=EVENT_UPLOADED_CLIENT_DOCUMENTS, db_index=True)
    period_start = models.DateField('Начало периода', db_index=True)
    period_end = models.DateField('Конец периода', db_index=True)
    credited_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Кто засчитал', on_delete=models.SET_NULL, null=True, blank=True, related_name='document_credits_created')
    credited_at = models.DateTimeField('Дата зачёта', default=timezone.now, db_index=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Зачёт загруженного клиента'
        verbose_name_plural = 'Зачёты загруженных клиентов'
        ordering = ['-credited_at']
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'client', 'event_type', 'period_start', 'period_end'],
                name='uniq_manager_client_document_credit_period',
            ),
        ]
        indexes = [
            models.Index(fields=['employee', 'period_start', 'period_end'], name='crm_mdoccredit_emp_period_idx'),
            models.Index(fields=['client', 'event_type'], name='crm_mdoccredit_client_idx'),
        ]

    def __str__(self):
        return f'{self.employee} +1 {self.client} ({self.period_start:%d.%m.%Y})'


class ClientQuestionnaire(TimeStampedModel):
    STATUS_DRAFT = 'draft'
    STATUS_COMPLETED = 'completed'
    STATUS_SUBMITTED = 'submitted'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_UPDATED = 'updated'
    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Не заполнена'),
        (STATUS_COMPLETED, 'Заполнена'),
        (STATUS_SUBMITTED, 'Отправлена на проверку'),
        (STATUS_APPROVED, 'Принята'),
        (STATUS_REJECTED, 'Отклонена'),
        (STATUS_UPDATED, 'Обновлена'),
    )

    client = models.OneToOneField(Client, verbose_name='Клиент', on_delete=models.CASCADE, related_name='questionnaire')
    mobile_questionnaire_id = models.PositiveIntegerField('Mobile questionnaire ID', null=True, blank=True, db_index=True)
    external_mobile_user_id = models.PositiveIntegerField('Mobile user ID', null=True, blank=True, db_index=True)
    source = models.CharField('Источник', max_length=80, blank=True, default='students_life_mobile_app')
    status = models.CharField('Статус анкеты', max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)

    full_name = models.CharField('ФИО', max_length=255, blank=True)
    phone = models.CharField('Телефон', max_length=80, blank=True)
    email = models.EmailField('Email', blank=True, null=True)
    citizenship = models.CharField('Гражданство', max_length=120, blank=True)
    desired_program = models.CharField('Желаемая программа / Вуз', max_length=255, blank=True)
    desired_country = models.CharField('Желаемая страна', max_length=120, blank=True)
    desired_city = models.CharField('Желаемый город', max_length=120, blank=True)
    face_photo_url = models.URLField('Фото абитуриента', max_length=1000, blank=True)
    data = models.JSONField('Данные анкеты', default=dict, blank=True)
    generated_file = models.FileField('Сгенерированный документ', upload_to=client_questionnaire_document_upload_to, blank=True, null=True)
    submitted_at = models.DateTimeField('Дата заполнения', null=True, blank=True)
    last_synced_at = models.DateTimeField('Последняя синхронизация', null=True, blank=True)

    @property
    def reviewed_at_external(self):
        return (self.data or {}).get('reviewed_at') or ''

    @property
    def reviewed_by_display(self):
        data = self.data or {}
        return data.get('reviewed_by_display') or data.get('reviewed_by_name') or data.get('reviewed_by_email') or ''

    @property
    def reviewed_by_name(self):
        return (self.data or {}).get('reviewed_by_name') or ''

    @property
    def reviewed_by_email(self):
        return (self.data or {}).get('reviewed_by_email') or ''

    @property
    def review_comment(self):
        return (self.data or {}).get('review_comment') or (self.data or {}).get('comment') or ''

    class Meta:
        verbose_name = 'Анкета клиента'
        verbose_name_plural = 'Анкеты клиентов'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['status', 'updated_at']),
            models.Index(fields=['external_mobile_user_id']),
        ]

    def __str__(self):
        return f'Анкета: {self.full_name or self.client.full_name}'

    def generate_file(self):
        from copy import deepcopy

        from docx import Document
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt

        template_path = os.path.join(os.path.dirname(__file__), 'document_templates', 'anketa_students_life_template_v2.docx')
        document = Document(template_path) if os.path.exists(template_path) else Document()
        data = self.data or {}

        from .questionnaire_labels import (
            QUESTIONNAIRE_DOCUMENT_LABELS,
            QUESTIONNAIRE_INTERNAL_FIELDS,
            QUESTIONNAIRE_VALUE_LABELS,
            questionnaire_field_label,
            questionnaire_value_label,
        )

        labels = QUESTIONNAIRE_DOCUMENT_LABELS
        value_labels = QUESTIONNAIRE_VALUE_LABELS

        def render_value(value):
            try:
                if value in value_labels:
                    return value_labels[value]
            except TypeError:
                pass
            if value in (None, '', [], {}):
                return '-'
            if hasattr(value, 'strftime'):
                return timezone.localtime(value).strftime('%d.%m.%Y %H:%M') if hasattr(value, 'tzinfo') and value.tzinfo else value.strftime('%d.%m.%Y')
            if isinstance(value, list):
                items = []
                for item in value:
                    if isinstance(item, dict):
                        university = item.get('university_name')
                        programs = item.get('programs')
                        if university:
                            program_text = render_value(programs)
                            items.append(f'{university}: {program_text}' if programs else str(university))
                            continue
                        language = item.get('language') or item.get('name') or item.get('title')
                        level = item.get('level')
                        if language:
                            items.append(f'{language} - {questionnaire_value_label(level)}' if level else str(language))
                        else:
                            items.append('; '.join(
                                f'{questionnaire_field_label(key)}: {render_value(val)}'
                                for key, val in item.items()
                            ))
                    else:
                        items.append(str(questionnaire_value_label(item)))
                return '\n'.join(f'- {item}' for item in items) if items else '-' 
            if isinstance(value, dict):
                return '\n'.join(
                    f'{questionnaire_field_label(key)}: {render_value(val)}'
                    for key, val in value.items()
                    if key not in QUESTIONNAIRE_INTERNAL_FIELDS
                )
            return str(questionnaire_value_label(value))

        def clear_cell(cell):
            # The branded template contains nested demonstration tables in a
            # few cells. Clearing only paragraphs leaves the previous client's
            # data in the generated questionnaire, so remove nested tables too.
            for nested_table in list(cell._tc.findall(qn('w:tbl'))):
                cell._tc.remove(nested_table)
            for paragraph in cell.paragraphs:
                paragraph.clear()

        def set_cell(cell, value, bold=False, size=8):
            clear_cell(cell)
            run = cell.paragraphs[0].add_run(str(value or ''))
            run.bold = bold
            run.font.size = Pt(size)

        def set_pair(table, row_index, field_one, value_one, field_two=None, value_two=None):
            cells = table.rows[row_index].cells
            set_cell(cells[0], questionnaire_field_label(field_one), bold=True)
            set_cell(cells[3], render_value(value_one))
            if field_two and len(cells) > 6:
                set_cell(cells[5], questionnaire_field_label(field_two), bold=True)
                set_cell(cells[6], render_value(value_two))
            elif len(cells) > 6:
                set_cell(cells[5], '')
                set_cell(cells[6], '')

        def append_pair(table, field_one, value_one, field_two=None, value_two=None):
            table._tbl.append(deepcopy(table.rows[-1]._tr))
            cells = table.rows[-1].cells
            if len(cells) >= 4:
                set_cell(cells[0], questionnaire_field_label(field_one), bold=True)
                set_cell(cells[3], render_value(value_one))
                if field_two and len(cells) > 6:
                    set_cell(cells[5], questionnaire_field_label(field_two), bold=True)
                    set_cell(cells[6], render_value(value_two))
                elif len(cells) > 6:
                    set_cell(cells[5], '')
                    set_cell(cells[6], '')

        if len(document.tables) >= 14:
            tables = document.tables
            form_type = data.get('form_type') or data.get('application_type') or 'applicant'
            title = 'ПРЕДВАРИТЕЛЬНАЯ ЗАЯВКА ШКОЛЬНИКА' if form_type == 'school_student' else 'АНКЕТА АБИТУРИЕНТА'
            if document.sections[0].header.tables:
                header_cell = document.sections[0].header.tables[0].cell(0, 2)
                header_runs = [run for paragraph in header_cell.paragraphs for run in paragraph.runs]
                if len(header_runs) >= 3:
                    header_runs[0].text = title.capitalize()
                    header_runs[2].text = timezone.localtime(timezone.now()).strftime('%d.%m.%Y %H:%M')
            set_cell(
                tables[0].cell(0, 0),
                f'{title}\nПерсональная карточка для поступления и сопровождения\nДата формирования: {timezone.localtime(timezone.now()):%d.%m.%Y %H:%M}',
                bold=True,
                size=12,
            )
            set_cell(tables[0].cell(0, 1), 'ФОТО\n3 × 4 см\nФото см. по ссылке в карточке', bold=True)

            set_pair(tables[1], 1, 'full_name', data.get('full_name') or self.full_name, 'birth_date', data.get('birth_date'))
            set_pair(tables[1], 2, 'gender', data.get('gender'), 'citizenship', data.get('citizenship') or self.citizenship)
            set_pair(tables[1], 3, 'marital_status', data.get('marital_status'), 'is_conscript', data.get('is_conscript'))
            set_pair(tables[2], 1, 'residence_country', data.get('residence_country'), 'residence_region', data.get('residence_region'))
            set_pair(tables[2], 2, 'residence_city', data.get('residence_city'), 'residence_street', data.get('residence_street'))
            set_pair(tables[2], 3, 'residence_house', data.get('residence_house'), 'residence_postal_code', data.get('residence_postal_code'))
            if data.get('current_residence') or data.get('current_location'):
                append_pair(tables[2], 'current_residence', data.get('current_residence'), 'current_location', data.get('current_location'))
            passport_number = render_value(data.get('passport_number'))
            passport_status = []
            if 'has_international_passport' in data:
                passport_status.append(
                    f"Действующий: {render_value(data.get('has_international_passport'))}"
                )
            if 'passport_pending' in data:
                passport_status.append(
                    f"Оформляется: {render_value(data.get('passport_pending'))}"
                )
            passport_value = '\n'.join([passport_number, *passport_status])
            set_pair(tables[3], 1, 'passport_number', passport_value, 'passport_issued_by', data.get('passport_issued_by'))
            set_pair(tables[3], 2, 'passport_issue_date', data.get('passport_issue_date'), 'passport_expiry_date', data.get('passport_expiry_date'))
            tables[3]._tbl.remove(tables[3].rows[3]._tr)
            set_pair(tables[4], 1, 'phone', data.get('phone') or self.phone, 'email', data.get('email') or self.email)
            set_pair(tables[4], 2, 'extra_phone', data.get('extra_phone'), 'imo', data.get('imo'))
            set_pair(tables[4], 3, 'telegram', data.get('telegram'), 'preferred_contact_method', data.get('preferred_contact_method'))
            set_pair(tables[5], 1, 'parent_full_name', data.get('parent_full_name'), 'parent_relation', data.get('parent_relation'))
            set_pair(tables[5], 2, 'parent_contacts', data.get('parent_contacts'), 'parent_workplace', data.get('parent_workplace'))
            set_pair(tables[5], 3, 'family_members', data.get('family_members'))
            set_pair(tables[6], 1, 'education_level', data.get('education_level'), 'school_name', data.get('school_name'))
            set_pair(tables[6], 2, 'school_country', data.get('school_country'), 'school_city', data.get('school_city'))
            set_pair(tables[6], 3, 'graduation_year', data.get('graduation_year'), 'education_status', data.get('education_status'))
            if data.get('school_class'):
                append_pair(tables[6], 'school_class', data.get('school_class'))
            set_pair(tables[7], 1, 'desired_program', data.get('desired_program') or self.desired_program, 'admission_goal', data.get('admission_goal'))
            set_pair(tables[7], 2, 'desired_city', data.get('desired_city') or self.desired_city, 'desired_country', data.get('desired_country') or self.desired_country)
            set_pair(tables[7], 3, 'desired_language', data.get('desired_language'), 'desired_education_level', data.get('desired_education_level'))
            set_pair(tables[7], 4, 'admission_urgency', data.get('admission_urgency'), 'academic_year', data.get('academic_year') or self.client.academic_year)
            if data.get('desired_universities'):
                append_pair(tables[7], 'desired_universities', data.get('desired_universities'))
            if data.get('university_choices'):
                append_pair(tables[7], 'university_choices', data.get('university_choices'))
            append_pair(tables[7], 'funding_type', data.get('funding_type') or self.client.funding_type, 'requested_services', data.get('requested_services'))
            set_pair(tables[8], 1, 'has_visa', data.get('has_visa'))
            if data.get('visa_country') or data.get('visa_city'):
                append_pair(tables[8], 'visa_country', data.get('visa_country'), 'visa_city', data.get('visa_city'))
            if data.get('visa_valid_until'):
                append_pair(tables[8], 'visa_valid_until', data.get('visa_valid_until'))
            set_pair(tables[9], 1, 'referral_source', data.get('referral_source'))
            if data.get('hobbies'):
                append_pair(tables[9], 'hobbies', data.get('hobbies'))
            if data.get('applicant_comment'):
                append_pair(tables[9], 'applicant_comment', data.get('applicant_comment'))
            if data.get('request_text'):
                append_pair(tables[9], 'request_text', data.get('request_text'))
            append_pair(tables[9], 'data_processing_consent', data.get('data_processing_consent'))
            languages = data.get('languages') or [{'language': 'Не указано', 'level': '-'}]
            language_row = deepcopy(tables[10].rows[1]._tr)
            for row in list(tables[10].rows[1:]):
                tables[10]._tbl.remove(row._tr)
            for item in languages:
                tables[10]._tbl.append(deepcopy(language_row))
                cells = tables[10].rows[-1].cells
                language = item.get('language') if isinstance(item, dict) else str(item)
                level = item.get('level') if isinstance(item, dict) else '-'
                set_cell(cells[0], language, bold=True)
                set_cell(cells[3], render_value(level))
            if data.get('achievements'):
                set_cell(tables[11].rows[1].cells[0], render_value(data.get('achievements')))
            else:
                tables[11]._element.getparent().remove(tables[11]._element)
            if data.get('help_needed'):
                set_cell(tables[12].rows[1].cells[0], render_value(data.get('help_needed')))
            else:
                tables[12]._element.getparent().remove(tables[12]._element)
            set_pair(tables[13], 1, 'status', self.get_status_display())
            set_pair(tables[13], 2, 'generated_document_at', timezone.now())
            manager_section_number = 11 + int(bool(data.get('achievements'))) + int(bool(data.get('help_needed')))
            set_cell(tables[13].rows[0].cells[0], str(manager_section_number), bold=True)
            set_cell(
                tables[13].rows[3].cells[0],
                'Подпись менеджера\n________________________',
                bold=True,
            )
            set_cell(
                tables[13].rows[3].cells[5],
                'Подпись абитуриента / представителя\n________________________',
                bold=True,
            )
            tables[13]._tbl.remove(tables[13].rows[4]._tr)
            # The explanatory footer row otherwise spills alone onto a blank
            # fourth page in LibreOffice and Word previews.
            if len(tables[13].rows) > 4:
                tables[13]._tbl.remove(tables[13].rows[4]._tr)
        else:
            section = document.sections[0]
            section.top_margin = Inches(0.47)
            section.bottom_margin = Inches(0.5)
            section.left_margin = Inches(0.5)
            section.right_margin = Inches(0.5)
            table = document.add_table(rows=0, cols=2)
            table.style = 'Table Grid'
            for field, value in data.items():
                if field in QUESTIONNAIRE_INTERNAL_FIELDS:
                    continue
                row = table.add_row().cells
                set_cell(row[0], questionnaire_field_label(field), bold=True)
                set_cell(row[1], render_value(value))

        buffer = io.BytesIO()
        document.save(buffer)
        filename = f'anketa-{self.client_id}-{uuid4().hex[:8]}.docx'
        self.generated_file.save(filename, ContentFile(buffer.getvalue()), save=False)
        self.save(update_fields=['generated_file', 'updated_at'])
        return self.generated_file
