# analytics/services.py
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from users.models import ManagerSalary
from .models import Payment, TransactionHistory


class BillingService:
    @staticmethod
    def confirm_payment(payment: Payment, admin_user):
        """
        Безопасное подтверждение платежа:
        - блокировка записи платежа
        - защита от двойного подтверждения
        - защита от двойного начисления бонуса
        """
        with transaction.atomic():
            locked_payment = (
                Payment.objects
                .select_for_update()
                .select_related('deal', 'deal__client', 'manager')
                .get(pk=payment.pk)
            )

            if locked_payment.is_confirmed:
                return locked_payment

            locked_payment.is_confirmed = True
            locked_payment.confirmed_by = admin_user
            locked_payment.confirmed_at = timezone.now()
            locked_payment.save(update_fields=[
                'is_confirmed',
                'confirmed_by',
                'confirmed_at',
                'updated_at',
            ])

            manager = locked_payment.manager
            if not hasattr(manager, 'managersalary'):
                return locked_payment

            salary_profile = ManagerSalary.objects.select_for_update().get(manager=manager)

            already_exists = TransactionHistory.objects.filter(
                reference_payment=locked_payment
            ).exists()

            if not already_exists:
                base_amount = (
                    locked_payment.net_income_usd
                    if locked_payment.net_income_usd and locked_payment.net_income_usd > 0
                    else locked_payment.amount_usd
                )
                bonus = (base_amount * salary_profile.commission_percent) / Decimal('100.00')

                if bonus > 0:
                    TransactionHistory.objects.create(
                        manager=manager,
                        amount=bonus,
                        reference_payment=locked_payment,
                        description=(
                            f"Комиссия {salary_profile.commission_percent}% "
                            f"за подтверждённый платёж #{locked_payment.id} "
                            f"(Сделка #{locked_payment.deal_id})"
                        )
                    )

                    salary_profile.current_balance += bonus
                    salary_profile.save(update_fields=['current_balance'])

            return locked_payment