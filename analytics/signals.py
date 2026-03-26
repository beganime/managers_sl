# analytics/signals.py
from decimal import Decimal

from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Payment


def recalculate_deal_and_manager(payment: Payment):
    deal = payment.deal

    confirmed_total = (
        deal.payments.filter(is_confirmed=True)
        .aggregate(total=Sum('amount_usd'))
        .get('total') or Decimal('0.00')
    )

    has_pending = deal.payments.filter(is_confirmed=False).exists()

    deal.paid_amount_usd = confirmed_total

    total_to_pay = deal.total_to_pay_usd or Decimal('0.00')
    if confirmed_total <= 0:
        deal.payment_status = 'waiting_payment' if has_pending else 'new'
    elif confirmed_total >= (total_to_pay - Decimal('0.01')):
        deal.payment_status = 'paid_full'
    else:
        deal.payment_status = 'paid_partial'

    deal.save(update_fields=['paid_amount_usd', 'payment_status', 'updated_at'])

    manager = payment.manager
    if hasattr(manager, 'managersalary'):
        month_revenue = (
            Payment.objects.filter(
                manager=manager,
                is_confirmed=True,
                payment_date__year=payment.payment_date.year,
                payment_date__month=payment.payment_date.month,
            )
            .aggregate(total=Sum('amount_usd'))
            .get('total') or Decimal('0.00')
        )

        manager.managersalary.current_month_revenue = month_revenue
        manager.managersalary.save(update_fields=['current_month_revenue'])


@receiver(post_save, sender=Payment)
def sync_after_payment_save(sender, instance, **kwargs):
    recalculate_deal_and_manager(instance)


@receiver(post_delete, sender=Payment)
def sync_after_payment_delete(sender, instance, **kwargs):
    recalculate_deal_and_manager(instance)