from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ActiveModel, TimeStampedModel
from apps.organizations.models import Company, Department, Office, Position


class EmployeeRole(TimeStampedModel, ActiveModel):
    ROLE_TYPE_CHOICES = (
        ('company_owner', 'Владелец компании'),
        ('office_director', 'Директор офиса'),
        ('manager', 'Менеджер'),
        ('accountant', 'Бухгалтер'),
        ('hr', 'HR'),
        ('viewer', 'Наблюдатель'),
    )

    code = models.SlugField('Код роли', max_length=64, unique=True)
    name = models.CharField('Название роли', max_length=150)
    role_type = models.CharField('Тип роли', max_length=32, choices=ROLE_TYPE_CHOICES, db_index=True)
    description = models.TextField('Описание', blank=True)

    class Meta:
        verbose_name = 'Роль сотрудника'
        verbose_name_plural = 'Роли сотрудников'
        ordering = ['name']

    def __str__(self):
        return self.name


class EmployeeProfile(TimeStampedModel, ActiveModel):
    WORK_STATUS_CHOICES = (
        ('working', 'Работает'),
        ('vacation', 'В отпуске'),
        ('sick', 'На больничном'),
        ('fired', 'Уволен'),
        ('paused', 'Приостановлен'),
    )

    SALARY_TYPE_CHOICES = (
        ('fixed', 'Фиксированный оклад'),
        ('commission', 'Только комиссия'),
        ('mixed', 'Оклад + комиссия'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователь',
        on_delete=models.CASCADE,
        related_name='employee_profile',
    )
    company = models.ForeignKey(
        Company,
        verbose_name='Компания',
        on_delete=models.PROTECT,
        related_name='employees',
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Офис',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    department = models.ForeignKey(
        Department,
        verbose_name='Отдел',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    position = models.ForeignKey(
        Position,
        verbose_name='Должность',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
    )
    role = models.ForeignKey(
        EmployeeRole,
        verbose_name='Роль доступа',
        on_delete=models.PROTECT,
        related_name='employees',
    )
    work_status = models.CharField('Рабочий статус', max_length=32, choices=WORK_STATUS_CHOICES, default='working')
    hire_date = models.DateField('Дата приёма', default=timezone.localdate)
    fired_date = models.DateField('Дата увольнения', null=True, blank=True)
    salary_type = models.CharField('Тип зарплаты', max_length=32, choices=SALARY_TYPE_CHOICES, default='mixed')
    fixed_salary = models.DecimalField('Оклад USD', max_digits=10, decimal_places=2, default=Decimal('0.00'))
    commission_percent = models.DecimalField('Процент комиссии', max_digits=5, decimal_places=2, default=Decimal('0.00'))
    rating = models.DecimalField('Рейтинг', max_digits=7, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField('Заметки', blank=True)

    class Meta:
        verbose_name = 'Профиль сотрудника'
        verbose_name_plural = 'Профили сотрудников'
        ordering = ['company__name', 'office__city', 'user__first_name', 'user__last_name']

    def __str__(self):
        full_name = self.user.get_full_name() or self.user.email
        return f'{full_name} — {self.company}'


class EmployeeAccess(TimeStampedModel):
    employee = models.OneToOneField(
        EmployeeProfile,
        verbose_name='Сотрудник',
        on_delete=models.CASCADE,
        related_name='access',
    )
    can_see_all_company = models.BooleanField('Видит всю компанию', default=False)
    can_see_all_office = models.BooleanField('Видит весь офис', default=False)
    can_manage_finance = models.BooleanField('Может управлять финансами', default=False)
    can_manage_hr = models.BooleanField('Может управлять сотрудниками', default=False)
    can_manage_documents = models.BooleanField('Может управлять документами', default=False)
    can_manage_catalog = models.BooleanField('Может управлять каталогом вузов', default=False)
    can_be_in_leaderboard = models.BooleanField('Показывать в рейтинге', default=True)
    must_track_workday = models.BooleanField('Обязан отмечать рабочий день', default=True)

    class Meta:
        verbose_name = 'Права сотрудника'
        verbose_name_plural = 'Права сотрудников'

    def __str__(self):
        return f'Права: {self.employee}'


class EmployeeRating(TimeStampedModel):
    employee = models.ForeignKey(
        EmployeeProfile,
        verbose_name='Сотрудник',
        on_delete=models.CASCADE,
        related_name='rating_logs',
    )
    date = models.DateField('Дата', default=timezone.localdate, db_index=True)
    score = models.DecimalField('Балл', max_digits=7, decimal_places=2, default=Decimal('0.00'))
    source = models.CharField('Источник', max_length=100, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'История рейтинга'
        verbose_name_plural = 'История рейтинга'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.employee} — {self.score} ({self.date})'
