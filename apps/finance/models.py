from decimal import Decimal, ROUND_HALF_UP

from django.apps import apps
from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.models import ActiveModel, TimeStampedModel
from apps.crm.models import Application, Client
from apps.education.models import Currency
from apps.erp_services.models import Service
from apps.organizations.models import Company, Office


MONEY_ZERO = Decimal('0.00')
RATE_ONE = Decimal('1.000000')


def money(value):
    return (value or MONEY_ZERO).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_currency_rate(currency):
    if currency and currency.rate_to_usd:
        return currency.rate_to_usd
    return RATE_ONE


def convert_to_usd(amount, currency=None, exchange_rate=None):
    rate = exchange_rate or get_currency_rate(currency)
    return money((amount or MONEY_ZERO) * rate)


class Cashbox(TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.PROTECT,
        related_name='finance_cashboxes',
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='finance_cashboxes',
        null=True,
        blank=True,
    )
    name = models.CharField('Name', max_length=150)
    currency = models.ForeignKey(
        Currency,
        verbose_name='Currency',
        on_delete=models.PROTECT,
        related_name='finance_cashboxes',
    )
    balance = models.DecimalField('Balance', max_digits=14, decimal_places=2, default=MONEY_ZERO)

    class Meta:
        verbose_name = 'Cashbox'
        verbose_name_plural = 'Cashboxes'
        ordering = ['company__name', 'office__name', 'name']
        unique_together = [('company', 'office', 'name')]
        indexes = [
            models.Index(fields=['company', 'office', 'is_active']),
        ]

    def __str__(self):
        return f'{self.name} ({self.currency.code})'


class Deal(TimeStampedModel):
    DEAL_TYPE_UNIVERSITY = 'university'
    DEAL_TYPE_SERVICE = 'service'
    DEAL_TYPE_OTHER = 'other'
    DEAL_TYPE_CHOICES = (
        (DEAL_TYPE_UNIVERSITY, 'University'),
        (DEAL_TYPE_SERVICE, 'Service'),
        (DEAL_TYPE_OTHER, 'Other'),
    )

    PAYMENT_STATUS_NEW = 'new'
    PAYMENT_STATUS_PARTIAL = 'paid_partial'
    PAYMENT_STATUS_FULL = 'paid_full'
    PAYMENT_STATUS_REFUNDED = 'refunded'
    PAYMENT_STATUS_CANCELLED = 'cancelled'
    PAYMENT_STATUS_CHOICES = (
        (PAYMENT_STATUS_NEW, 'New'),
        (PAYMENT_STATUS_PARTIAL, 'Partially paid'),
        (PAYMENT_STATUS_FULL, 'Paid in full'),
        (PAYMENT_STATUS_REFUNDED, 'Refunded'),
        (PAYMENT_STATUS_CANCELLED, 'Cancelled'),
    )

    company = models.ForeignKey(
        Company,
        verbose_name='Company',
        on_delete=models.PROTECT,
        related_name='finance_deals',
    )
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='finance_deals',
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        Client,
        verbose_name='Client',
        on_delete=models.PROTECT,
        related_name='finance_deals',
    )
    application = models.ForeignKey(
        Application,
        verbose_name='Application',
        on_delete=models.SET_NULL,
        related_name='finance_deals',
        null=True,
        blank=True,
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Manager',
        on_delete=models.PROTECT,
        related_name='finance_deals',
    )
    deal_type = models.CharField('Deal type', max_length=32, choices=DEAL_TYPE_CHOICES, default=DEAL_TYPE_SERVICE, db_index=True)
    university_name = models.CharField('University name', max_length=255, blank=True)
    program_name = models.CharField('Program name', max_length=255, blank=True)
    service = models.ForeignKey(
        Service,
        verbose_name='Service',
        on_delete=models.SET_NULL,
        related_name='finance_deals',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, db_index=True)
    currency = models.ForeignKey(
        Currency,
        verbose_name='Currency',
        on_delete=models.PROTECT,
        related_name='finance_deals',
    )
    price_client = models.DecimalField('Client price', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    expected_revenue_usd = models.DecimalField('Expected revenue USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    total_to_pay_usd = models.DecimalField('Total to pay USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    paid_amount_usd = models.DecimalField('Paid amount USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    payment_status = models.CharField('Payment status', max_length=32, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_NEW, db_index=True)
    comment = models.TextField('Comment', blank=True)
    custom_data = models.JSONField('Custom data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Deal'
        verbose_name_plural = 'Deals'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'payment_status']),
            models.Index(fields=['manager', 'payment_status']),
            models.Index(fields=['client', 'payment_status']),
            models.Index(fields=['deal_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.total_to_pay_usd = convert_to_usd(self.price_client, self.currency)
        if not self.expected_revenue_usd:
            self.expected_revenue_usd = self.total_to_pay_usd
        super().save(*args, **kwargs)

    def refresh_payment_totals(self, save=True):
        paid = self.payments.filter(is_confirmed=True).aggregate(total=Sum('amount_usd'))['total'] or MONEY_ZERO
        self.paid_amount_usd = money(paid)

        if self.payment_status not in {self.PAYMENT_STATUS_REFUNDED, self.PAYMENT_STATUS_CANCELLED}:
            if self.paid_amount_usd <= MONEY_ZERO:
                self.payment_status = self.PAYMENT_STATUS_NEW
            elif self.paid_amount_usd < self.total_to_pay_usd:
                self.payment_status = self.PAYMENT_STATUS_PARTIAL
            else:
                self.payment_status = self.PAYMENT_STATUS_FULL

        if save:
            self.save(update_fields=['paid_amount_usd', 'payment_status', 'total_to_pay_usd', 'updated_at'])


class Payment(TimeStampedModel):
    METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('bank', 'Bank'),
        ('transfer', 'Transfer'),
        ('online', 'Online'),
        ('other', 'Other'),
    )

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='finance_payments')
    office = models.ForeignKey(Office, verbose_name='Office', on_delete=models.SET_NULL, related_name='finance_payments', null=True, blank=True)
    deal = models.ForeignKey(Deal, verbose_name='Deal', on_delete=models.CASCADE, related_name='payments')
    client = models.ForeignKey(Client, verbose_name='Client', on_delete=models.PROTECT, related_name='finance_payments')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Manager', on_delete=models.PROTECT, related_name='finance_payments')
    cashbox = models.ForeignKey(Cashbox, verbose_name='Cashbox', on_delete=models.SET_NULL, related_name='payments', null=True, blank=True)
    amount = models.DecimalField('Amount', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    currency = models.ForeignKey(Currency, verbose_name='Currency', on_delete=models.PROTECT, related_name='finance_payments')
    exchange_rate = models.DecimalField('Exchange rate to USD', max_digits=14, decimal_places=6, default=RATE_ONE)
    amount_usd = models.DecimalField('Amount USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    method = models.CharField('Method', max_length=32, choices=METHOD_CHOICES, default='cash', db_index=True)
    payment_date = models.DateField('Payment date', default=timezone.localdate, db_index=True)
    proof_file = models.FileField('Proof file', upload_to='finance/payment_proofs/', null=True, blank=True)
    is_confirmed = models.BooleanField('Confirmed', default=False, db_index=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Confirmed by',
        on_delete=models.SET_NULL,
        related_name='confirmed_finance_payments',
        null=True,
        blank=True,
    )
    confirmed_at = models.DateTimeField('Confirmed at', null=True, blank=True)
    comment = models.TextField('Comment', blank=True)

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-payment_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'is_confirmed']),
            models.Index(fields=['manager', 'payment_date']),
            models.Index(fields=['client', 'payment_date']),
            models.Index(fields=['payment_date']),
        ]

    def __str__(self):
        return f'{self.client} - {self.amount} {self.currency.code}'

    def save(self, *args, **kwargs):
        if not self.exchange_rate or self.exchange_rate == RATE_ONE:
            self.exchange_rate = get_currency_rate(self.currency)
        self.amount_usd = convert_to_usd(self.amount, self.currency, self.exchange_rate)
        super().save(*args, **kwargs)

    def confirm(self, user=None):
        if self.is_confirmed:
            return self

        with transaction.atomic():
            self.is_confirmed = True
            self.confirmed_by = user
            self.confirmed_at = timezone.now()
            self.save(update_fields=['is_confirmed', 'confirmed_by', 'confirmed_at', 'exchange_rate', 'amount_usd', 'updated_at'])

            if self.cashbox_id:
                Cashbox.objects.filter(pk=self.cashbox_id).update(balance=models.F('balance') + self.amount)

            self.deal.refresh_payment_totals(save=True)
            Transaction.objects.get_or_create(
                related_payment=self,
                transaction_type=Transaction.TYPE_PAYMENT,
                defaults={
                    'company': self.company,
                    'office': self.office,
                    'cashbox': self.cashbox,
                    'amount': self.amount,
                    'currency': self.currency,
                    'amount_usd': self.amount_usd,
                    'created_by': user,
                    'comment': self.comment,
                },
            )
        return self


class ExpenseCategory(TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.CASCADE, related_name='finance_expense_categories')
    name = models.CharField('Name', max_length=150)
    code = models.SlugField('Code', max_length=80)

    class Meta:
        verbose_name = 'Expense category'
        verbose_name_plural = 'Expense categories'
        ordering = ['company__name', 'name']
        unique_together = [('company', 'code')]
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return self.name


class Expense(TimeStampedModel):
    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='finance_expenses')
    office = models.ForeignKey(Office, verbose_name='Office', on_delete=models.SET_NULL, related_name='finance_expenses', null=True, blank=True)
    category = models.ForeignKey(ExpenseCategory, verbose_name='Category', on_delete=models.PROTECT, related_name='expenses')
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Employee',
        on_delete=models.SET_NULL,
        related_name='finance_expenses',
        null=True,
        blank=True,
    )
    cashbox = models.ForeignKey(Cashbox, verbose_name='Cashbox', on_delete=models.SET_NULL, related_name='expenses', null=True, blank=True)
    title = models.CharField('Title', max_length=255, db_index=True)
    amount = models.DecimalField('Amount', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    currency = models.ForeignKey(Currency, verbose_name='Currency', on_delete=models.PROTECT, related_name='finance_expenses')
    exchange_rate = models.DecimalField('Exchange rate to USD', max_digits=14, decimal_places=6, default=RATE_ONE)
    amount_usd = models.DecimalField('Amount USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    date = models.DateField('Date', default=timezone.localdate, db_index=True)
    proof_file = models.FileField('Proof file', upload_to='finance/expense_proofs/', null=True, blank=True)
    is_confirmed = models.BooleanField('Confirmed', default=False, db_index=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Confirmed by',
        on_delete=models.SET_NULL,
        related_name='confirmed_finance_expenses',
        null=True,
        blank=True,
    )
    confirmed_at = models.DateTimeField('Confirmed at', null=True, blank=True)
    comment = models.TextField('Comment', blank=True)

    class Meta:
        verbose_name = 'Expense'
        verbose_name_plural = 'Expenses'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'is_confirmed']),
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.exchange_rate or self.exchange_rate == RATE_ONE:
            self.exchange_rate = get_currency_rate(self.currency)
        self.amount_usd = convert_to_usd(self.amount, self.currency, self.exchange_rate)
        super().save(*args, **kwargs)

    def confirm(self, user=None):
        if self.is_confirmed:
            return self

        with transaction.atomic():
            self.is_confirmed = True
            self.confirmed_by = user
            self.confirmed_at = timezone.now()
            self.save(update_fields=['is_confirmed', 'confirmed_by', 'confirmed_at', 'exchange_rate', 'amount_usd', 'updated_at'])

            if self.cashbox_id:
                Cashbox.objects.filter(pk=self.cashbox_id).update(balance=models.F('balance') - self.amount)

            Transaction.objects.get_or_create(
                related_expense=self,
                transaction_type=Transaction.TYPE_EXPENSE,
                defaults={
                    'company': self.company,
                    'office': self.office,
                    'cashbox': self.cashbox,
                    'amount': self.amount,
                    'currency': self.currency,
                    'amount_usd': self.amount_usd,
                    'created_by': user,
                    'comment': self.comment,
                },
            )
        return self


class Income(TimeStampedModel):
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending confirmation'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_REJECTED, 'Rejected'),
    )

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='finance_incomes')
    office = models.ForeignKey(Office, verbose_name='Office', on_delete=models.SET_NULL, related_name='finance_incomes', null=True, blank=True)
    cashbox = models.ForeignKey(Cashbox, verbose_name='Cashbox', on_delete=models.PROTECT, related_name='incomes')
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Employee',
        on_delete=models.SET_NULL,
        related_name='finance_incomes',
        null=True,
        blank=True,
    )
    client = models.ForeignKey(
        Client,
        verbose_name='Client',
        on_delete=models.SET_NULL,
        related_name='finance_incomes',
        null=True,
        blank=True,
    )
    deal = models.ForeignKey(
        Deal,
        verbose_name='Deal',
        on_delete=models.SET_NULL,
        related_name='finance_incomes',
        null=True,
        blank=True,
    )
    service = models.ForeignKey(
        Service,
        verbose_name='Service',
        on_delete=models.SET_NULL,
        related_name='finance_incomes',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, db_index=True)
    amount = models.DecimalField('Amount', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    currency = models.ForeignKey(Currency, verbose_name='Currency', on_delete=models.PROTECT, related_name='finance_incomes')
    exchange_rate = models.DecimalField('Exchange rate to USD', max_digits=14, decimal_places=6, default=RATE_ONE)
    amount_usd = models.DecimalField('Amount USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    date = models.DateField('Date', default=timezone.localdate, db_index=True)
    source = models.CharField('Source', max_length=150, blank=True)
    proof_file = models.FileField('Proof file', upload_to='finance/income_proofs/', null=True, blank=True)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    is_confirmed = models.BooleanField('Confirmed', default=False, db_index=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Confirmed by',
        on_delete=models.SET_NULL,
        related_name='confirmed_finance_incomes',
        null=True,
        blank=True,
    )
    confirmed_at = models.DateTimeField('Confirmed at', null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Rejected by',
        on_delete=models.SET_NULL,
        related_name='rejected_finance_incomes',
        null=True,
        blank=True,
    )
    rejected_at = models.DateTimeField('Rejected at', null=True, blank=True)
    rejection_reason = models.TextField('Rejection reason', blank=True)
    comment = models.TextField('Comment', blank=True)

    class Meta:
        verbose_name = 'Income'
        verbose_name_plural = 'Incomes'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.exchange_rate or self.exchange_rate == RATE_ONE:
            self.exchange_rate = get_currency_rate(self.currency)
        self.amount_usd = convert_to_usd(self.amount, self.currency, self.exchange_rate)
        super().save(*args, **kwargs)

    def confirm(self, user=None):
        if self.is_confirmed:
            return self

        with transaction.atomic():
            self.is_confirmed = True
            self.status = self.STATUS_CONFIRMED
            self.confirmed_by = user
            self.confirmed_at = timezone.now()
            self.rejection_reason = ''
            self.save(update_fields=[
                'is_confirmed',
                'status',
                'confirmed_by',
                'confirmed_at',
                'rejection_reason',
                'exchange_rate',
                'amount_usd',
                'updated_at',
            ])

            Cashbox.objects.filter(pk=self.cashbox_id).update(balance=models.F('balance') + self.amount)
            Transaction.objects.get_or_create(
                related_income=self,
                transaction_type=Transaction.TYPE_INCOME,
                defaults={
                    'company': self.company,
                    'office': self.office,
                    'cashbox': self.cashbox,
                    'amount': self.amount,
                    'currency': self.currency,
                    'amount_usd': self.amount_usd,
                    'created_by': user,
                    'comment': self.comment or self.source,
                },
            )

            if self.employee_id:
                commission_amount = money(self.amount_usd * Decimal('0.05'))
                EmployeeCommission.objects.get_or_create(
                    income=self,
                    employee=self.employee,
                    defaults={
                        'company': self.company,
                        'office': self.office,
                        'deal': self.deal,
                        'percent': Decimal('5.00'),
                        'amount_usd': commission_amount,
                        'status': 'approved',
                        'approved_by': user,
                        'approved_at': timezone.now(),
                    },
                )
                employee_model = self.employee.__class__
                if any(field.name == 'current_balance' for field in employee_model._meta.fields):
                    employee_model.objects.filter(pk=self.employee_id).update(current_balance=models.F('current_balance') + commission_amount)
                manager_salary_model = apps.get_model('users', 'ManagerSalary')
                salary, _ = manager_salary_model.objects.get_or_create(manager=self.employee)
                manager_salary_model.objects.filter(pk=salary.pk).update(current_balance=models.F('current_balance') + commission_amount)
        return self

    def reject(self, user=None, reason=''):
        if self.is_confirmed:
            return self
        self.status = self.STATUS_REJECTED
        self.rejected_by = user
        self.rejected_at = timezone.now()
        self.rejection_reason = reason or ''
        self.save(update_fields=['status', 'rejected_by', 'rejected_at', 'rejection_reason', 'updated_at'])
        return self


class Transaction(TimeStampedModel):
    TYPE_INCOME = 'income'
    TYPE_EXPENSE = 'expense'
    TYPE_PAYMENT = 'payment'
    TYPE_TRANSFER_IN = 'transfer_in'
    TYPE_TRANSFER_OUT = 'transfer_out'
    TYPE_CORRECTION = 'correction'
    TYPE_CHOICES = (
        (TYPE_INCOME, 'Income'),
        (TYPE_EXPENSE, 'Expense'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_TRANSFER_IN, 'Transfer in'),
        (TYPE_TRANSFER_OUT, 'Transfer out'),
        (TYPE_CORRECTION, 'Correction'),
    )

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='finance_transactions')
    office = models.ForeignKey(Office, verbose_name='Office', on_delete=models.SET_NULL, related_name='finance_transactions', null=True, blank=True)
    cashbox = models.ForeignKey(Cashbox, verbose_name='Cashbox', on_delete=models.PROTECT, related_name='transactions', null=True, blank=True)
    transaction_type = models.CharField('Transaction type', max_length=32, choices=TYPE_CHOICES, db_index=True)
    amount = models.DecimalField('Amount', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    currency = models.ForeignKey(Currency, verbose_name='Currency', on_delete=models.PROTECT, related_name='finance_transactions')
    amount_usd = models.DecimalField('Amount USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    related_payment = models.ForeignKey(Payment, verbose_name='Related payment', on_delete=models.SET_NULL, related_name='transactions', null=True, blank=True)
    related_expense = models.ForeignKey(Expense, verbose_name='Related expense', on_delete=models.SET_NULL, related_name='transactions', null=True, blank=True)
    related_income = models.ForeignKey(Income, verbose_name='Related income', on_delete=models.SET_NULL, related_name='transactions', null=True, blank=True)
    comment = models.TextField('Comment', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='finance_transactions',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'transaction_type']),
            models.Index(fields=['cashbox', 'created_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.get_transaction_type_display()} - {self.amount} {self.currency.code}'


class EmployeeCommission(TimeStampedModel):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    )

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='finance_commissions')
    office = models.ForeignKey(Office, verbose_name='Office', on_delete=models.SET_NULL, related_name='finance_commissions', null=True, blank=True)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Employee', on_delete=models.PROTECT, related_name='finance_commissions')
    payment = models.ForeignKey(Payment, verbose_name='Payment', on_delete=models.CASCADE, related_name='commissions', null=True, blank=True)
    income = models.ForeignKey(Income, verbose_name='Income', on_delete=models.CASCADE, related_name='commissions', null=True, blank=True)
    deal = models.ForeignKey(Deal, verbose_name='Deal', on_delete=models.CASCADE, related_name='commissions', null=True, blank=True)
    percent = models.DecimalField('Percent', max_digits=5, decimal_places=2, default=MONEY_ZERO)
    amount_usd = models.DecimalField('Amount USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default='pending', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Approved by',
        on_delete=models.SET_NULL,
        related_name='approved_finance_commissions',
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField('Approved at', null=True, blank=True)
    paid_at = models.DateTimeField('Paid at', null=True, blank=True)

    class Meta:
        verbose_name = 'Employee commission'
        verbose_name_plural = 'Employee commissions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['employee', 'status']),
        ]

    def __str__(self):
        return f'{self.employee} - {self.amount_usd} USD'

    def save(self, *args, **kwargs):
        if not self.amount_usd and self.payment_id:
            self.amount_usd = money(self.payment.amount_usd * (self.percent or MONEY_ZERO) / Decimal('100'))
        if not self.amount_usd and self.income_id:
            self.amount_usd = money(self.income.amount_usd * (self.percent or MONEY_ZERO) / Decimal('100'))
        super().save(*args, **kwargs)


class FinancialPeriod(TimeStampedModel):
    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.CASCADE, related_name='finance_periods')
    office = models.ForeignKey(Office, verbose_name='Office', on_delete=models.SET_NULL, related_name='finance_periods', null=True, blank=True)
    start_date = models.DateField('Start date', db_index=True)
    end_date = models.DateField('End date', db_index=True)
    total_revenue_usd = models.DecimalField('Total revenue USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    total_expenses_usd = models.DecimalField('Total expenses USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    net_profit_usd = models.DecimalField('Net profit USD', max_digits=14, decimal_places=2, default=MONEY_ZERO)
    is_closed = models.BooleanField('Closed', default=False, db_index=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Closed by',
        on_delete=models.SET_NULL,
        related_name='closed_finance_periods',
        null=True,
        blank=True,
    )
    closed_at = models.DateTimeField('Closed at', null=True, blank=True)

    class Meta:
        verbose_name = 'Financial period'
        verbose_name_plural = 'Financial periods'
        ordering = ['-start_date']
        unique_together = [('company', 'office', 'start_date', 'end_date')]
        indexes = [
            models.Index(fields=['company', 'office', 'is_closed']),
            models.Index(fields=['start_date', 'end_date']),
        ]

    def __str__(self):
        scope = self.office or self.company
        return f'{scope}: {self.start_date} - {self.end_date}'

    def calculate(self, save=True):
        payment_filters = {
            'company': self.company,
            'is_confirmed': True,
            'payment_date__gte': self.start_date,
            'payment_date__lte': self.end_date,
        }
        expense_filters = {
            'company': self.company,
            'is_confirmed': True,
            'date__gte': self.start_date,
            'date__lte': self.end_date,
        }
        income_filters = {
            'company': self.company,
            'is_confirmed': True,
            'date__gte': self.start_date,
            'date__lte': self.end_date,
        }
        if self.office_id:
            payment_filters['office'] = self.office
            expense_filters['office'] = self.office
            income_filters['office'] = self.office

        payments_total = Payment.objects.filter(**payment_filters).aggregate(total=Sum('amount_usd'))['total'] or MONEY_ZERO
        incomes_total = Income.objects.filter(**income_filters).aggregate(total=Sum('amount_usd'))['total'] or MONEY_ZERO
        expenses_total = Expense.objects.filter(**expense_filters).aggregate(total=Sum('amount_usd'))['total'] or MONEY_ZERO

        self.total_revenue_usd = money(payments_total + incomes_total)
        self.total_expenses_usd = money(expenses_total)
        self.net_profit_usd = money(self.total_revenue_usd - self.total_expenses_usd)

        if save:
            self.save(update_fields=['total_revenue_usd', 'total_expenses_usd', 'net_profit_usd', 'updated_at'])
        return self

    def close(self, user=None):
        self.calculate(save=False)
        self.is_closed = True
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save(update_fields=[
            'total_revenue_usd',
            'total_expenses_usd',
            'net_profit_usd',
            'is_closed',
            'closed_by',
            'closed_at',
            'updated_at',
        ])
        return self
