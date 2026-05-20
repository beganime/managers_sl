from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ActiveModel, TimeStampedModel
from apps.organizations.models import Company, Office


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
    submitter_ip = models.GenericIPAddressField('IP отправителя', null=True, blank=True, db_index=True)
    submitter_user_agent = models.TextField('User-Agent', blank=True, default='')
    submitter_referer = models.URLField('Referer', max_length=1000, blank=True, default='')
    converted_at = models.DateTimeField('Дата конвертации', null=True, blank=True)

    class Meta:
        verbose_name = 'Лид'
        verbose_name_plural = 'Лиды'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['manager', 'status']),
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        return f'{self.full_name} ({self.phone})'

    def mark_converted(self):
        self.status = 'converted'
        self.converted_at = timezone.now()
        self.save(update_fields=['status', 'converted_at', 'updated_at'])


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
