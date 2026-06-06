from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import ActiveModel, OrderedModel, TimeStampedModel
from apps.organizations.models import Company


class Country(TimeStampedModel, ActiveModel, OrderedModel):
    name = models.CharField('Страна', max_length=120, unique=True)
    code = models.CharField('Код страны', max_length=8, blank=True, db_index=True)
    image = models.ImageField('Изображение', upload_to='erp/education/country_images/', blank=True, null=True)
    cover_image = models.ImageField('Обложка', upload_to='erp/education/country_covers/', blank=True, null=True)
    flag = models.ImageField('Флаг', upload_to='erp/education/flags/', blank=True, null=True)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'Страна обучения'
        verbose_name_plural = 'Страны обучения'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class City(TimeStampedModel, ActiveModel, OrderedModel):
    country = models.ForeignKey(Country, verbose_name='Страна', on_delete=models.CASCADE, related_name='cities')
    name = models.CharField('Город', max_length=120)
    image = models.ImageField('Изображение', upload_to='erp/education/city_images/', blank=True, null=True)
    cover_image = models.ImageField('Обложка', upload_to='erp/education/city_covers/', blank=True, null=True)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'Город обучения'
        verbose_name_plural = 'Города обучения'
        ordering = ['country__name', 'sort_order', 'name']
        unique_together = [('country', 'name')]

    def __str__(self):
        return f'{self.name}, {self.country.name}'


class Currency(TimeStampedModel):
    code = models.CharField('Код валюты', max_length=3, unique=True)
    name = models.CharField('Название валюты', max_length=80)
    symbol = models.CharField('Символ', max_length=8, default='$')
    rate_to_usd = models.DecimalField('Курс к USD', max_digits=14, decimal_places=6, default=Decimal('1.000000'))

    class Meta:
        verbose_name = 'Валюта'
        verbose_name_plural = 'Валюты'
        ordering = ['code']

    def __str__(self):
        return f'{self.code} ({self.rate_to_usd})'


class University(TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, verbose_name='Компания', on_delete=models.PROTECT, related_name='education_universities', null=True, blank=True)
    country = models.ForeignKey(Country, verbose_name='Страна', on_delete=models.PROTECT, related_name='universities')
    city = models.ForeignKey(City, verbose_name='Город', on_delete=models.SET_NULL, null=True, blank=True, related_name='universities')
    local_currency = models.ForeignKey(Currency, verbose_name='Валюта страны', on_delete=models.SET_NULL, null=True, blank=True, related_name='universities')
    name = models.CharField('Название ВУЗа', max_length=255, db_index=True)
    legal_name = models.CharField('Юридическое название', max_length=255, blank=True)
    logo = models.ImageField('Логотип', upload_to='erp/education/university_logos/', blank=True, null=True)
    cover_image = models.ImageField('Главное изображение', upload_to='erp/education/university_covers/', blank=True, null=True)
    website = models.URLField('Сайт', blank=True)
    email = models.EmailField('Email', blank=True)
    phone = models.CharField('Телефон', max_length=80, blank=True)
    address = models.CharField('Адрес', max_length=255, blank=True)
    description = models.TextField('Описание', blank=True)
    admission_requirements = models.TextField('Условия поступления', blank=True)
    invitation_info = models.TextField('Условия приглашения', blank=True)
    dormitory_info = models.TextField('Общежитие', blank=True)
    expenses_info = models.TextField('Расходы и проживание', blank=True)
    age_limit = models.CharField('Возрастные ограничения', max_length=100, blank=True)
    commission_info = models.TextField('Партнёрские условия / комиссия', blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Кем добавлен', on_delete=models.SET_NULL, null=True, blank=True, related_name='education_universities_added')
    custom_data = models.JSONField('Дополнительные данные', default=dict, blank=True)

    class Meta:
        verbose_name = 'ВУЗ'
        verbose_name_plural = 'ВУЗы'
        ordering = ['country__name', 'city__name', 'name']
        indexes = [
            models.Index(fields=['country', 'city', 'is_active']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f'{self.name} ({self.country.name})'


class Program(TimeStampedModel, ActiveModel):
    DEGREE_CHOICES = (
        ('school', 'Школа'),
        ('foundation', 'Foundation / подготовительный курс'),
        ('language', 'Языковые курсы'),
        ('bachelor', 'Бакалавриат'),
        ('specialist', 'Специалитет'),
        ('master', 'Магистратура'),
        ('phd', 'PhD / аспирантура'),
        ('other', 'Другое'),
    )

    university = models.ForeignKey(University, verbose_name='ВУЗ', on_delete=models.CASCADE, related_name='programs')
    name = models.CharField('Название программы', max_length=255, db_index=True)
    degree = models.CharField('Степень', max_length=32, choices=DEGREE_CHOICES, default='bachelor', db_index=True)
    faculty = models.CharField('Факультет', max_length=255, blank=True)
    language = models.CharField('Язык обучения', max_length=100, blank=True)
    duration = models.CharField('Длительность', max_length=100, blank=True)
    description = models.TextField('Описание', blank=True)
    admission_requirements = models.TextField('Требования', blank=True)
    is_archived = models.BooleanField('Архив', default=False, db_index=True)
    custom_data = models.JSONField('Дополнительные данные', default=dict, blank=True)

    class Meta:
        verbose_name = 'Программа обучения'
        verbose_name_plural = 'Программы обучения'
        ordering = ['university__name', 'degree', 'name']
        indexes = [
            models.Index(fields=['university', 'degree', 'is_active']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f'{self.name} — {self.university.name}'


class ProgramFee(TimeStampedModel):
    program = models.ForeignKey(Program, verbose_name='Программа', on_delete=models.CASCADE, related_name='fees')
    currency = models.ForeignKey(Currency, verbose_name='Валюта', on_delete=models.PROTECT, related_name='program_fees')
    tuition_fee = models.DecimalField('Стоимость обучения', max_digits=14, decimal_places=2, default=Decimal('0.00'))
    service_fee_usd = models.DecimalField('Стоимость услуг компании USD', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    application_fee = models.DecimalField('Application fee', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    dormitory_fee = models.DecimalField('Общежитие', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    insurance_fee = models.DecimalField('Страховка', max_digits=12, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField('Примечание', blank=True)

    class Meta:
        verbose_name = 'Стоимость программы'
        verbose_name_plural = 'Стоимость программ'
        ordering = ['program__university__name', 'program__name', '-created_at']

    def __str__(self):
        return f'{self.program} — {self.tuition_fee} {self.currency.code}'


class Intake(TimeStampedModel, ActiveModel):
    program = models.ForeignKey(Program, verbose_name='Программа', on_delete=models.CASCADE, related_name='intakes')
    title = models.CharField('Название набора', max_length=150)
    start_date = models.DateField('Дата начала', null=True, blank=True)
    application_deadline = models.DateField('Дедлайн подачи', null=True, blank=True)
    notes = models.TextField('Примечание', blank=True)

    class Meta:
        verbose_name = 'Набор / intake'
        verbose_name_plural = 'Наборы / intakes'
        ordering = ['program__university__name', 'start_date']

    def __str__(self):
        return f'{self.program} — {self.title}'


class RequiredDocument(TimeStampedModel, ActiveModel, OrderedModel):
    university = models.ForeignKey(University, verbose_name='ВУЗ', on_delete=models.CASCADE, related_name='required_documents', null=True, blank=True)
    program = models.ForeignKey(Program, verbose_name='Программа', on_delete=models.CASCADE, related_name='required_documents', null=True, blank=True)
    title = models.CharField('Название документа', max_length=255)
    description = models.TextField('Описание', blank=True)
    is_mandatory = models.BooleanField('Обязательный', default=True)

    class Meta:
        verbose_name = 'Требуемый документ'
        verbose_name_plural = 'Требуемые документы'
        ordering = ['sort_order', 'title']

    def __str__(self):
        return self.title


class UniversityContact(TimeStampedModel, ActiveModel):
    university = models.ForeignKey(University, verbose_name='ВУЗ', on_delete=models.CASCADE, related_name='contact_people')
    full_name = models.CharField('ФИО', max_length=255, blank=True)
    position = models.CharField('Должность', max_length=255, blank=True)
    email = models.EmailField('Email', blank=True)
    phone = models.CharField('Телефон', max_length=80, blank=True)
    messenger = models.CharField('Мессенджер', max_length=120, blank=True)
    notes = models.TextField('Заметки', blank=True)

    class Meta:
        verbose_name = 'Контакт ВУЗа'
        verbose_name_plural = 'Контакты ВУЗов'
        ordering = ['university__name', 'full_name']

    def __str__(self):
        return f'{self.university.name}: {self.full_name or self.email or self.phone}'
