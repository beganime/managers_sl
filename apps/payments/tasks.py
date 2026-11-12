from celery import shared_task
from django.db import transaction

from .models import Payment, PaymentRecipient


def queue_payment_admins_notification(payment: Payment) -> None:
    """После коммита транзакции отправляет админам Telegram-уведомление."""
    payment_id = payment.pk
    transaction.on_commit(lambda: notify_payment_admins.delay(payment_id))


@shared_task(
    bind=True,
    name='payments.notify_admins',
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 6},
)
def notify_payment_admins(self, payment_id: int) -> dict:
    from apps.attendance.telegram import send_telegram_message
    from apps.attendance.models import EmployeeTelegramAccount

    payment = (
        Payment.objects
        .select_related('manager', 'client')
        .filter(pk=payment_id)
        .first()
    )
    if payment is None:
        return {'sent': False, 'reason': 'payment_missing'}

    accounts = {
        account.employee_id: account
        for account in EmployeeTelegramAccount.objects.filter(
            employee_id__in=PaymentRecipient.objects.values_list('user_id', flat=True),
            is_active=True,
        )
    }
    manager_name = payment.manager.get_full_name() or payment.manager.email
    message = (
        '💳 Новая оплата на проверке\n'
        f'Менеджер: {manager_name}\n'
        f'Клиент: {payment.client.full_name}\n'
        f'Сумма: {payment.amount}\n'
        f'Дата: {payment.created_at:%d.%m.%Y %H:%M}\n'
        'Проверить: https://manager-sl.ru/portal/payments/admin/'
    )
    sent = 0
    failed = []
    for employee_id, account in accounts.items():
        ok, error = send_telegram_message(message, account.chat_id)
        if ok:
            sent += 1
        else:
            failed.append(f'{employee_id}:{error}')
    if not accounts:
        raise self.retry(countdown=180)
    return {'sent': sent, 'failed': failed}
