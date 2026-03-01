# analytics/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from .models import Payment, Deal, TransactionHistory

@receiver(post_save, sender=Payment)
def update_deal_and_manager_financials(sender, instance, created, **kwargs):
    """
    1. Автоматически пересчитывает сумму оплаты в сделке.
    2. Обновляет KPI менеджера (выручку за месяц).
    3. Начисляет бонусный баланс при подтверждении.
    """
    deal = instance.deal
    
    # === 1. ОБНОВЛЕНИЕ СТАТУСА СДЕЛКИ ===
    # Считаем только подтвержденные платежи
    total_paid = sum((p.amount_usd or 0) for p in deal.payments.filter(is_confirmed=True))
    deal.paid_amount_usd = total_paid
    
    total_to_pay = float(deal.total_to_pay_usd or 0)
    
    if deal.paid_amount_usd <= 0:
        deal.payment_status = 'new'
    elif total_to_pay > 0 and float(deal.paid_amount_usd) >= (total_to_pay - 0.01):
        deal.payment_status = 'paid_full'
    else:
        deal.payment_status = 'paid_partial'
        
    deal.save()


    # === 2. ОБНОВЛЕНИЕ ФИНАНСОВ МЕНЕДЖЕРА ===
    manager = instance.manager
    if hasattr(manager, 'managersalary'):
        salary_profile = manager.managersalary
        
        # Пересчитываем выручку за текущий месяц (надежно, через Sum)
        today = timezone.now().date()
        start_of_month = today.replace(day=1)
        
        monthly_payments = Payment.objects.filter(
            manager=manager,
            is_confirmed=True,
            payment_date__gte=start_of_month
        )
        total_revenue = monthly_payments.aggregate(Sum('amount_usd'))['amount_usd__sum'] or Decimal('0.00')
        salary_profile.current_month_revenue = total_revenue
        
        # === 3. НАЧИСЛЕНИЕ БОНУСА (Только если платеж подтвержден) ===
        if instance.is_confirmed:
            # Проверяем в Истории Транзакций, не начисляли ли мы уже бонус за ЭТОТ платеж
            transaction_exists = TransactionHistory.objects.filter(reference_payment=instance).exists()
            
            if not transaction_exists:
                # Считаем процент от суммы платежа (amount_usd)
                # Если у вас принято считать от net_income_usd, просто замените instance.amount_usd на instance.net_income_usd
                bonus_amount = instance.amount_usd * (salary_profile.commission_percent / Decimal('100.00'))
                
                # Создаем запись в историю для прозрачности
                TransactionHistory.objects.create(
                    manager=manager,
                    amount=bonus_amount,
                    reference_payment=instance,
                    description=f"Комиссия {salary_profile.commission_percent}% за платеж #{instance.id} (Сделка #{deal.id})"
                )
                
                # Прибавляем сумму к балансу "к выплате"
                salary_profile.add_commission(bonus_amount)
        
        salary_profile.save()