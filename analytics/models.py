import calendar
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum
from datetime import date
from decimal import Decimal
from catalog.models import Currency, University, Program
from services.models import Service

# --- СДЕЛКИ (DEALS) ---
class Deal(models.Model):
    TYPE_CHOICES = (
        ('university', 'Поступление в ВУЗ'),
        ('service', 'Доп. услуга (Виза/Билет)'),
    )
    
    STATUS_CHOICES = (
        ('new', 'Новая'),
        ('process', 'В процессе'),
        ('waiting_payment', 'Ожидает оплаты'),
        ('paid_partial', 'Частично оплачена'),
        ('paid_full', 'Полностью оплачена'),
        ('closed', 'Закрыта'),
    )

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='deals', verbose_name="Клиент")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Менеджер")
    deal_type = models.CharField("Тип сделки", max_length=20, choices=TYPE_CHOICES)
    
    university = models.ForeignKey(University, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="ВУЗ")
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Программа")
    
    service_ref = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Услуга из каталога")
    custom_service_name = models.CharField("Название услуги (Ручное)", max_length=255, blank=True)
    custom_service_desc = models.TextField("Описание действий менеджера", blank=True)
    
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, verbose_name="Валюта сделки")
    price_client = models.DecimalField("Цена для клиента (в валюте)", max_digits=12, decimal_places=2)
    
    expected_revenue_usd = models.DecimalField("Ожидаемая выручка компании (USD)", max_digits=10, decimal_places=2, default=0.00)
    
    total_to_pay_usd = models.DecimalField("Итого к оплате (USD)", max_digits=12, decimal_places=2, help_text="Авто-конвертация")
    paid_amount_usd = models.DecimalField("Уже оплачено (USD)", max_digits=12, decimal_places=2, default=0.00)
    payment_status = models.CharField("Статус оплаты", max_length=20, choices=STATUS_CHOICES, default='new')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # 1. Автоматический расчет итоговой оплаты в USD
        if self.currency:
            if self.currency.code == 'USD':
                self.total_to_pay_usd = self.price_client
            else:
                self.total_to_pay_usd = self.price_client / self.currency.rate
        else:
            self.total_to_pay_usd = self.price_client

        # 2. Автоматический расчет ожидаемой выручки компании
        if self.deal_type == 'university' and self.program:
            self.expected_revenue_usd = self.program.service_fee
        elif self.deal_type == 'service' and self.service_ref:
            self.expected_revenue_usd = self.total_to_pay_usd - self.service_ref.real_cost
        elif not self.expected_revenue_usd:
            self.expected_revenue_usd = Decimal('0.00')

        super().save(*args, **kwargs)

    def __str__(self):
        # 3. Подробное отображение для списка выбора в Платежах
        return f"Сделка #{self.id} | Клиент: {self.client.full_name} | К оплате: {self.total_to_pay_usd}$ | Оплачено: {self.paid_amount_usd}$"

    class Meta:
        verbose_name = "Сделка"
        verbose_name_plural = "Сделки"


# --- ПЛАТЕЖИ (PAYMENTS) ---
class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Наличные'),
        ('card', 'Карта'),
        ('bank', 'Банковский перевод'),
    )

    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name='payments', verbose_name="Сделка")
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Кто принял платеж")
    
    amount = models.DecimalField("Сумма платежа", max_digits=12, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, verbose_name="Валюта платежа")
    
    exchange_rate = models.DecimalField("Курс конвертации", max_digits=10, decimal_places=4, editable=False)
    amount_usd = models.DecimalField("Сумма в USD", max_digits=12, decimal_places=2, editable=False)
    
    net_income_usd = models.DecimalField("Чистый доход компании с платежа (USD)", max_digits=12, decimal_places=2, help_text="Сколько реально заработали")
    
    payment_date = models.DateField("Дата платежа", default=timezone.now)
    method = models.CharField("Способ оплаты", max_length=20, choices=PAYMENT_METHOD_CHOICES)
    
    is_confirmed = models.BooleanField("Подтверждено Администрацией", default=False)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='confirmed_payments', on_delete=models.SET_NULL, null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.exchange_rate:
            self.exchange_rate = self.currency.rate
        
        if self.currency.code == 'USD':
             self.amount_usd = self.amount
        else:
             self.amount_usd = self.amount / self.exchange_rate
             
        # 7. Авто-расчет чистого дохода (пропорционально сумме платежа)
        if self.deal and self.deal.total_to_pay_usd > 0:
            profit_ratio = self.deal.expected_revenue_usd / self.deal.total_to_pay_usd
            self.net_income_usd = self.amount_usd * profit_ratio
        else:
            self.net_income_usd = Decimal('0.00')
             
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"


# --- ИСТОРИЯ ТРАНЗАКЦИЙ ---
class TransactionHistory(models.Model):
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField("Сумма (USD)", max_digits=10, decimal_places=2)
    reference_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Основание (Платеж)")
    description = models.CharField("Описание", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.manager} -> {self.amount}$ ({self.created_at.strftime('%d.%m')})"

    class Meta:
        verbose_name = "История начислений"
        verbose_name_plural = "История начислений"
        ordering = ['-created_at']


# --- РАСХОДЫ ---
class Expense(models.Model):
    title = models.CharField("Название расхода", max_length=255)
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    amount_usd = models.DecimalField("Сумма в USD", max_digits=12, decimal_places=2, editable=False)
    
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name="Кто потратил")
    date = models.DateField(default=timezone.now)
    
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if self.currency.code == 'USD':
             self.amount_usd = self.amount
        else:
             self.amount_usd = self.amount / self.currency.rate
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Расход фирмы"
        verbose_name_plural = "Расходы фирмы"


# --- ОТЧЕТНОСТЬ ---
class FinancialPeriod(models.Model):
    start_date = models.DateField("Начало периода", unique=True)
    end_date = models.DateField("Конец периода")
    
    total_revenue = models.DecimalField("Всего выручка (USD)", max_digits=15, decimal_places=2, default=0.00)
    total_expenses = models.DecimalField("Всего расходы (USD)", max_digits=15, decimal_places=2, default=0.00)
    net_profit = models.DecimalField("Чистая прибыль (Котёл)", max_digits=15, decimal_places=2, default=0.00)
    
    is_closed = models.BooleanField("Период закрыт", default=False, help_text="Если закрыт - зарплаты выплачены/обнулены")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Период {self.start_date} - {self.end_date}"

    @staticmethod
    def get_period_dates(current_date=None):
        if not current_date:
            current_date = date.today()
        
        year = current_date.year
        month = current_date.month
        
        if current_date.day <= 15:
            start = date(year, month, 1)
            end = date(year, month, 15)
        else:
            start = date(year, month, 16)
            last_day = calendar.monthrange(year, month)[1]
            end = date(year, month, last_day)
        
        return start, end

    @classmethod
    def ensure_current_period(cls):
        start, end = cls.get_period_dates()
        obj, created = cls.objects.get_or_create(
            start_date=start,
            defaults={'end_date': end}
        )
        return obj

    def calculate_stats(self):
        all_confirmed_payments = Payment.objects.filter(
            payment_date__range=(self.start_date, self.end_date),
            is_confirmed=True
        )
        
        calc_revenue = all_confirmed_payments.aggregate(Sum('amount_usd'))['amount_usd__sum'] or 0
        calc_net_income = all_confirmed_payments.aggregate(Sum('net_income_usd'))['net_income_usd__sum'] or 0
        
        calc_expenses = Expense.objects.filter(
            date__range=(self.start_date, self.end_date)
        ).aggregate(Sum('amount_usd'))['amount_usd__sum'] or 0
        
        final_profit = calc_net_income - calc_expenses
        
        self.total_revenue = float(calc_revenue)
        self.total_expenses = float(calc_expenses)
        self.net_profit = float(final_profit)
        self.save() 

        return {
            "calc_revenue": float(calc_revenue),
            "calc_expenses": float(calc_expenses),
            "final_profit": float(final_profit)
        }

    class Meta:
        verbose_name = "Финансовый отчет (Период)"
        verbose_name_plural = "Финансовые отчеты"

from django.contrib.admin.models import LogEntry

class AuditLog(LogEntry):
    class Meta:
        proxy = True 
        verbose_name = "История действий"
        verbose_name_plural = "История действий"
        app_label = 'analytics'