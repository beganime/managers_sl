from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from catalog.models import Currency


class OfficeFinanceEntry(models.Model):
    ENTRY_TYPES = (
        ('income', 'Доход'),
        ('expense', 'Расход'),
    )

    ENTRY_CATEGORIES = (
        ('custom', 'Другое'),
        ('salary', 'Зарплата'),
        ('visa', 'Виза'),
        ('air_tickets', 'Авиабилеты'),
        ('office', 'Офис'),
        ('utilities', 'Коммунальные расходы'),
        ('marketing', 'Маркетинг'),
    )

    office = models.ForeignKey(
        'users.Office',
        on_delete=models.CASCADE,
        related_name='finance_entries',
        verbose_name='Офис',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_finance_entries',
        verbose_name='Создал',
    )
    entry_type = models.CharField(
        'Тип операции',
        max_length=20,
        choices=ENTRY_TYPES,
        db_index=True,
    )
    title = models.CharField('Название', max_length=255)
    category = models.CharField(
        'Категория',
        max_length=100,
        choices=ENTRY_CATEGORIES,
        default='custom',
        db_index=True,
    )
    comment = models.TextField('Комментарий', blank=True)
    amount = models.DecimalField('Сумма', max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        verbose_name='Валюта',
        related_name='office_finance_entries',
    )
    exchange_rate = models.DecimalField(
        'Курс к USD',
        max_digits=12,
        decimal_places=6,
        default=1,
    )
    amount_usd = models.DecimalField(
        'Сумма в USD',
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    entry_date = models.DateField('Дата операции', default=timezone.localdate)
    is_confirmed = models.BooleanField('Подтверждено', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Офисная финансовая операция'
        verbose_name_plural = 'Офисные финансовые операции'
        ordering = ('-entry_date', '-created_at')

    def __str__(self):
        return f'{self.get_entry_type_display()}: {self.title}'

    def save(self, *args, **kwargs):
        rate = Decimal(str(self.exchange_rate or 0))
        if not rate or rate <= 0:
            rate = Decimal(str(getattr(self.currency, 'rate', 1) or 1))
            self.exchange_rate = rate

        amount = Decimal(str(self.amount or 0))
        if rate > 0:
            self.amount_usd = (amount / rate).quantize(Decimal('0.01'))
        else:
            self.amount_usd = amount.quantize(Decimal('0.01'))

        super().save(*args, **kwargs)


def summarize_office_finances(office, date_from=None, date_to=None, category=None):
    qs = OfficeFinanceEntry.objects.filter(office=office, is_confirmed=True)

    if date_from:
        qs = qs.filter(entry_date__gte=date_from)

    if date_to:
        qs = qs.filter(entry_date__lte=date_to)

    if category:
        qs = qs.filter(category=category)

    income = qs.filter(entry_type='income').aggregate(total=Sum('amount_usd'))['total'] or Decimal('0')
    expense = qs.filter(entry_type='expense').aggregate(total=Sum('amount_usd'))['total'] or Decimal('0')

    return {
        'income_usd': Decimal(str(income)).quantize(Decimal('0.01')),
        'expense_usd': Decimal(str(expense)).quantize(Decimal('0.01')),
        'net_usd': (Decimal(str(income)) - Decimal(str(expense))).quantize(Decimal('0.01')),
    }