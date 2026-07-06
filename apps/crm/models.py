import io
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from apps.core.models import ActiveModel, TimeStampedModel
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


class ClientQuestionnaire(TimeStampedModel):
    STATUS_DRAFT = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_UPDATED = 'updated'
    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Не заполнена'),
        (STATUS_SUBMITTED, 'Заполнена'),
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
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        document = Document()
        title = document.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title.add_run("Student's Life\nАнкета абитуриента")
        run.bold = True
        run.font.size = Pt(18)
        document.add_paragraph(f'Дата формирования: {timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")}')

        sections = [
            ('Личные данные', ('full_name', 'birth_date', 'gender', 'citizenship', 'marital_status')),
            ('Адрес проживания', ('residence_country', 'residence_region', 'residence_city', 'residence_street', 'residence_house', 'residence_postal_code')),
            ('Паспортные данные', ('passport_number', 'passport_issued_by', 'passport_issue_date', 'passport_expiry_date', 'has_international_passport')),
            ('Контакты', ('phone', 'email', 'extra_phone', 'imo', 'telegram', 'preferred_contact_method')),
            ('Родители / представители', ('parent_full_name', 'parent_relation', 'parent_contacts', 'parent_workplace', 'family_members')),
            ('Образование', ('education_level', 'school_class', 'school_name', 'school_country', 'school_city', 'graduation_year', 'education_status')),
            ('Поступление', ('desired_program', 'admission_goal', 'desired_city', 'desired_country', 'desired_language', 'desired_education_level', 'admission_urgency')),
            ('Виза', ('has_visa', 'visa_country', 'visa_city', 'visa_valid_until')),
            ('Дополнительно', ('hobbies', 'applicant_comment', 'referral_source')),
        ]
        labels = {
            'full_name': 'ФИО',
            'birth_date': 'Дата рождения',
            'gender': 'Пол',
            'citizenship': 'Гражданство',
            'marital_status': 'Семейное положение',
            'residence_country': 'Страна',
            'residence_region': 'Регион',
            'residence_city': 'Город',
            'residence_street': 'Улица',
            'residence_house': 'Дом / квартира',
            'residence_postal_code': 'Почтовый индекс',
            'passport_number': 'Паспорт',
            'passport_issued_by': 'Где оформлен',
            'passport_issue_date': 'Дата начала действия',
            'passport_expiry_date': 'Дата окончания действия',
            'has_international_passport': 'Загранпаспорт',
            'phone': 'Телефон',
            'email': 'Email',
            'extra_phone': 'Доп. телефон',
            'imo': 'Imo',
            'telegram': 'Telegram',
            'preferred_contact_method': 'Способ связи',
            'parent_full_name': 'ФИО родителя',
            'parent_relation': 'Кем является',
            'parent_contacts': 'Контакты родителя',
            'parent_workplace': 'Работа родителя',
            'family_members': 'Семья',
            'education_level': 'Уровень образования',
            'school_class': 'Класс',
            'school_name': 'Учебное заведение',
            'school_country': 'Страна учебы',
            'school_city': 'Город учебы',
            'graduation_year': 'Год окончания',
            'education_status': 'Статус',
            'desired_program': 'Программа / Вуз',
            'admission_goal': 'Цель',
            'desired_city': 'Город',
            'desired_country': 'Страна',
            'desired_language': 'Язык обучения',
            'desired_education_level': 'Уровень обучения',
            'admission_urgency': 'Срочность',
            'has_visa': 'Виза',
            'visa_country': 'Страна визы',
            'visa_city': 'Город визы',
            'visa_valid_until': 'Срок визы',
            'hobbies': 'Хобби',
            'applicant_comment': 'Комментарий',
            'referral_source': 'Источник',
        }

        for section_title, fields in sections:
            document.add_heading(section_title, level=2)
            table = document.add_table(rows=0, cols=2)
            table.style = 'Table Grid'
            for field in fields:
                value = self.data.get(field)
                if value in (None, '', []):
                    continue
                row = table.add_row().cells
                row[0].text = labels.get(field, field)
                row[1].text = str(value)

        for list_title, field in (('Достижения', 'achievements'), ('Языки', 'languages'), ('Нужна помощь с', 'help_needed')):
            value = self.data.get(field) or []
            if not value:
                continue
            document.add_heading(list_title, level=2)
            if isinstance(value, list):
                for item in value:
                    document.add_paragraph(str(item), style='List Bullet')
            else:
                document.add_paragraph(str(value))

        buffer = io.BytesIO()
        document.save(buffer)
        filename = f'anketa-{self.client_id}-{uuid4().hex[:8]}.docx'
        self.generated_file.save(filename, ContentFile(buffer.getvalue()), save=False)
        self.save(update_fields=['generated_file', 'updated_at'])
        return self.generated_file
