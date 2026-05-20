from django.conf import settings
from django.db import models

from apps.core.models import ActiveModel, OrderedModel, TimeStampedModel


class Company(TimeStampedModel, ActiveModel):
    """Юридическое лицо / компания внутри ERP."""

    name = models.CharField('Название компании', max_length=255, db_index=True)
    legal_name = models.CharField('Юридическое название', max_length=255, blank=True)
    registration_number = models.CharField('ИНН / регистрационный номер', max_length=100, blank=True)
    country = models.CharField('Страна', max_length=100, default='Россия')
    city = models.CharField('Город', max_length=100, blank=True)
    address = models.CharField('Адрес', max_length=255, blank=True)
    phone = models.CharField('Телефон', max_length=50, blank=True)
    email = models.EmailField('Email', blank=True)
    website = models.URLField('Сайт', blank=True)
    logo = models.ImageField('Логотип', upload_to='erp/companies/logos/', blank=True, null=True)
    stamp = models.ImageField('Печать', upload_to='erp/companies/stamps/', blank=True, null=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Владелец / главный ответственный',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_erp_companies',
    )
    notes = models.TextField('Заметки', blank=True)

    class Meta:
        verbose_name = 'Компания'
        verbose_name_plural = 'Компании'
        ordering = ['name']

    def __str__(self):
        return self.name


class Office(TimeStampedModel, ActiveModel):
    """Филиал / офис компании."""

    company = models.ForeignKey(
        Company,
        verbose_name='Компания',
        on_delete=models.CASCADE,
        related_name='offices',
    )
    name = models.CharField('Название офиса', max_length=255)
    country = models.CharField('Страна', max_length=100, default='Россия')
    city = models.CharField('Город', max_length=100, db_index=True)
    address = models.CharField('Адрес', max_length=255, blank=True)
    phone = models.CharField('Телефон офиса', max_length=50, blank=True)
    email = models.EmailField('Email офиса', blank=True)
    director = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Руководитель офиса',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='directed_erp_offices',
    )
    timezone = models.CharField('Часовой пояс', max_length=64, default='Asia/Ashgabat')
    notes = models.TextField('Заметки', blank=True)

    class Meta:
        verbose_name = 'Офис'
        verbose_name_plural = 'Офисы'
        ordering = ['company__name', 'city', 'name']
        unique_together = [('company', 'name', 'city')]

    def __str__(self):
        return f'{self.name} — {self.city}'


class Department(TimeStampedModel, ActiveModel, OrderedModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Компания',
        on_delete=models.CASCADE,
        related_name='departments',
    )
    name = models.CharField('Название отдела', max_length=150)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'Отдел'
        verbose_name_plural = 'Отделы'
        ordering = ['company__name', 'sort_order', 'name']
        unique_together = [('company', 'name')]

    def __str__(self):
        return self.name


class Position(TimeStampedModel, ActiveModel, OrderedModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Компания',
        on_delete=models.CASCADE,
        related_name='positions',
    )
    department = models.ForeignKey(
        Department,
        verbose_name='Отдел',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='positions',
    )
    name = models.CharField('Должность', max_length=150)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'Должность'
        verbose_name_plural = 'Должности'
        ordering = ['company__name', 'department__name', 'sort_order', 'name']
        unique_together = [('company', 'department', 'name')]

    def __str__(self):
        return self.name
