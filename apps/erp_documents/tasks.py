import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.attendance.models import EmployeeTelegramAccount
from apps.attendance.telegram import send_telegram_message
from apps.erp_notifications.services import create_notification
from apps.payments.models import PaymentRecipient

from .models import GeneratedDocument

logger = logging.getLogger(__name__)


def _document_message(document: GeneratedDocument) -> str:
    manager_name = ''
    if document.manager_id:
        manager_name = (document.manager.get_full_name() or document.manager.email).strip()
    client_name = str(document.client) if document.client_id else '—'
    lines = [
        '📄 Новый документ в ManagerSL',
        f'Шаблон: {document.template.name}',
        f'Клиент: {client_name}',
        f'Менеджер: {manager_name or "—"}',
        f'Статус: {document.get_status_display()}',
        f'Открыть: {settings.PORTAL_BASE_URL}/portal/documents/{document.pk}/',
    ]
    return '\n'.join(lines)


@shared_task(bind=True, name='erp_documents.notify_document_admins', autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 6})
def notify_document_admins(self, document_id: int) -> dict:
    """Шлёт Telegram-уведомление админам (получатели оплат) о новом документе.

    Повторяет попытку, пока ни у одного получателя нет привязанного Telegram.
    """
    document = GeneratedDocument.objects.select_related('template', 'client', 'manager', 'company', 'office').filter(pk=document_id).first()
    if document is None:
        return {'sent': False, 'reason': 'document_missing'}

    recipient_ids = list(PaymentRecipient.objects.values_list('user_id', flat=True))
    if not recipient_ids:
        raise self.retry(countdown=180)

    accounts = {
        account.employee_id: account
        for account in EmployeeTelegramAccount.objects.filter(employee_id__in=recipient_ids, is_active=True)
    }
    if not accounts:
        raise self.retry(countdown=180)

    message = _document_message(document)
    sent = 0
    failed = []
    for employee_id, account in accounts.items():
        ok, error = send_telegram_message(message, account.chat_id)
        if ok:
            sent += 1
        else:
            failed.append(f'{employee_id}:{error}')

    # Дублируем в портал: in-app запись об уведомлении для истории.
    from django.contrib.auth import get_user_model

    for recipient in get_user_model().objects.filter(id__in=recipient_ids):
        create_notification(
            recipient,
            title='Новый документ',
            body=f'{document.template.name} — {str(document.client) if document.client_id else "без клиента"}.',
            channel='in_app',
            queue=False,
            target_url=f'/portal/documents/{document.pk}/',
            company=document.company,
            office=document.office,
        )
    return {'sent': sent, 'failed': failed}
