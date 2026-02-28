# analytics/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Payment, Deal

@receiver(post_save, sender=Payment)
def update_deal_payment_status(sender, instance, **kwargs):
    """
    Автоматически пересчитывает сумму оплаты в сделке.
    Срабатывает при любом сохранении платежа (создание, редактирование, подтверждение).
    """
    deal = instance.deal
    
    # Считаем только подтвержденные платежи (защита от None в amount_usd)
    total_paid = sum((p.amount_usd or 0) for p in deal.payments.filter(is_confirmed=True))
    deal.paid_amount_usd = total_paid
    
    # Защита от Null в total_to_pay_usd
    total_to_pay = float(deal.total_to_pay_usd or 0)
    
    # Определяем статус
    # Используем небольшую дельту (0.01) для сравнения float/decimal
    if deal.paid_amount_usd <= 0:
        deal.payment_status = 'new'
    elif total_to_pay > 0 and float(deal.paid_amount_usd) >= (total_to_pay - 0.01):
        deal.payment_status = 'paid_full'
    else:
        deal.payment_status = 'paid_partial'
        
    deal.save()