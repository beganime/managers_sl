from django.db import transaction
from django.db.models import F
from django.utils import timezone
from users.models import ManagerSalary
from .models import Payment, TransactionHistory

class BillingService:
    @staticmethod
    def confirm_payment(payment: Payment, admin_user):
        """
        Безопасное подтверждение платежа с начислением бонусов.
        Выполняется в одной транзакции: или всё, или ничего.
        """
        # Если уже подтвержден — пропускаем, чтобы не начислить дважды
        if payment.is_confirmed:
            return

        with transaction.atomic():
            # 1. Фиксируем платеж
            payment.is_confirmed = True
            payment.confirmed_by = admin_user
            payment.confirmed_at = timezone.now()
            payment.save()

            # 2. Находим менеджера и его кошелек
            manager = payment.manager
            if hasattr(manager, 'managersalary'):
                salary_profile = ManagerSalary.objects.select_for_update().get(manager=manager)
                
                # Расчет бонуса
                percent = salary_profile.commission_percent / 100
                base_amount = payment.net_income_usd if payment.net_income_usd > 0 else payment.amount_usd
                bonus = base_amount * percent

                # 3. Атомарное обновление баланса (защита от Race Condition)
                # Мы не делаем balance += bonus, мы шлем инструкцию в БД
                salary_profile.current_balance = F('current_balance') + bonus
                salary_profile.current_month_revenue = F('current_month_revenue') + payment.amount_usd
                salary_profile.save()

                # 4. Пишем лог транзакции (Аудит)
                TransactionHistory.objects.create(
                    manager=manager,
                    amount=bonus,
                    reference_payment=payment,
                    description=f"Бонус за платеж #{payment.id} (Клиент: {payment.deal.client.full_name})"
                )