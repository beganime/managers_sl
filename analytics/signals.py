# analytics/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
from .models import Payment, Deal

@receiver(post_save, sender=Payment)
def update_deal_payment_status(sender, instance, **kwargs):
    """
    Автоматически пересчитывает сумму оплаты в сделке.
    Срабатывает при любом сохранении платежа (создание, редактирование, подтверждение).
    """
    deal = instance.deal
    
    # Считаем только подтвержденные платежи, инициируем как Decimal
    total_paid = sum((p.amount_usd for p in deal.payments.filter(is_confirmed=True)), Decimal('0.00'))
    deal.paid_amount_usd = total_paid
    
    # Определяем статус (Используем Decimal для корректного математического сравнения)
    delta = Decimal('0.01')
    
    if deal.paid_amount_usd <= Decimal('0.00'):
        deal.payment_status = 'new'
    elif deal.paid_amount_usd >= (deal.total_to_pay_usd - delta):
        deal.payment_status = 'paid_full'
    else:
        deal.payment_status = 'paid_partial'
        
    deal.save()