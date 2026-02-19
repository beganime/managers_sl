import calendar
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum
from datetime import date
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

    def __str__(self):
        return f"Сделка #{self.id} - {self.client} ({self.get_deal_type_display()})"

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

    def save(self, *args, **kwargs):
        # Фиксируем курс только при создании или если он не задан
        if not self.exchange_rate:
            self.exchange_rate = self.currency.rate
        
        # Расчет суммы в USD
        if self.currency.code == 'USD':
             self.amount_usd = self.amount
        else:
             self.amount_usd = self.amount / self.exchange_rate
             
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"


# --- ИСТОРИЯ ТРАНЗАКЦИЙ (NEW) ---
class TransactionHistory(models.Model):
    """
    Аудит начислений. Показывает, откуда взялись деньги на балансе менеджера.
    """
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField("Сумма (USD)", max_digits=10, decimal_places=2)
    reference_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Основание (Платеж)")
    description = models.CharField("Описание", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

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
    
    # Эти поля теперь заполняются явно, а не при каждом сохранении
    total_revenue = models.DecimalField("Всего выручка (USD)", max_digits=15, decimal_places=2, default=0.00)
    total_expenses = models.DecimalField("Всего расходы (USD)", max_digits=15, decimal_places=2, default=0.00)
    net_profit = models.DecimalField("Чистая прибыль (Котёл)", max_digits=15, decimal_places=2, default=0.00)
    
    is_closed = models.BooleanField("Период закрыт", default=False, help_text="Если закрыт - зарплаты выплачены/обнулены")
    created_at = models.DateTimeField(auto_now_add=True)

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
        """
        Тяжелый метод пересчета статистики. 
        Вызывать ТОЛЬКО при нажатии кнопки 'Обновить' или закрытии периода.
        """
        from clients.models import Client
        
        # Считаем только подтвержденные платежи
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
        
        # Обновляем поля модели
        self.total_revenue = float(calc_revenue)
        self.total_expenses = float(calc_expenses)
        self.net_profit = float(final_profit)
        self.save() # Сохраняем новые цифры в базу

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
    """
    Прокси-модель для Истории действий.
    Позволяет отобразить логи в разделе 'Analytics' и чинит доступ к ним.
    """
    class Meta:
        proxy = True # Не создает новую таблицу в БД, использует существующую
        verbose_name = "История действий"
        verbose_name_plural = "История действий"
        app_label = 'analytics' # <-- ВАЖНО: Привязываем к твоему приложению