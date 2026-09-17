"""Manual, explicit mailbox ownership using the existing external-account registry."""
import hashlib
from uuid import uuid4
from django.core.validators import validate_email
from django.db import connection, transaction
from django.db.models import Q, Count, Max
from apps.client_onboarding.models import ClientServiceIdentity
from .models import ActivityLog, Client, EmailRecord, ExternalAccount
from .external_accounts import create_external_account, ExternalAccountError


@transaction.atomic
def bind_mailbox(*, student, email, actor):
    email = str(email or '').strip().casefold()
    validate_email(email)
    if connection.vendor == 'postgresql':
        lock_id = int.from_bytes(hashlib.sha256(email.encode()).digest()[:8], 'big', signed=True)
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock_id])
    conflicts = Client.objects.filter(
        Q(email__iexact=email) | Q(external_accounts__system=ExternalAccount.SYSTEM_EMAIL, external_accounts__email__iexact=email)
    ).exclude(pk=student.pk).exists()
    conflicts |= ClientServiceIdentity.objects.filter(tmmail_email__iexact=email).exclude(client=student).exists()
    conflicts |= EmailRecord.objects.filter(mailbox__iexact=email, student__isnull=False).exclude(student=student).exists()
    if conflicts:
        raise ExternalAccountError('Этот адрес связан с другим клиентом. Проверьте адрес; автоматическая перепривязка запрещена.')
    account = ExternalAccount.objects.filter(student=student, system=ExternalAccount.SYSTEM_EMAIL, email__iexact=email).first()
    if account is None:
        account, _ = create_external_account(actor=actor, student=student, system=ExternalAccount.SYSTEM_EMAIL,
            provider_name=email, email=email, login=email, status=ExternalAccount.STATUS_CREATED,
            source_service='manager_mailbox', notes='Ручная привязка адреса. Подключение IMAP проверяется отдельно в SMTPSL.')
    records = EmailRecord.objects.filter(mailbox__iexact=email, student__isnull=True, application__isnull=True)
    count = records.update(student=student, responsible=student.manager)
    if count:
        ActivityLog.objects.create(event_id=uuid4(), actor=actor, service='manager_mailbox', student=student,
            object_type='crm.ExternalAccount', object_id=str(account.public_id), action='MAILBOX_HISTORY_LINKED',
            new_data={'email': email, 'linked_records': count})
    return account, count


def mailbox_overview(student):
    accounts = ExternalAccount.objects.filter(student=student, system=ExternalAccount.SYSTEM_EMAIL).order_by('email')
    stats = {row['mailbox'].casefold(): row for row in EmailRecord.objects.filter(student=student)
        .values('mailbox').annotate(total=Count('id'), latest=Max('received_at'), synchronized=Max('updated_at'))}
    return [{'email': account.email, 'status': account.get_status_display(), **stats.get(account.email.casefold(), {})}
        for account in accounts]
