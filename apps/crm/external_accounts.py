"""Canonical writes for RUID and other student external accounts."""

from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from .credentials import encrypt_external_secret
from .models import ActivityLog, ExternalAccount


class ExternalAccountError(ValueError):
    pass


def _event_uuid(value):
    if value in (None, ''):
        return uuid4()
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ExternalAccountError('event_id должен быть UUID.') from exc


def _validate_application(student, application):
    if application and application.client_id != student.pk:
        raise ExternalAccountError('Заявка должна принадлежать выбранному студенту.')


@transaction.atomic
def create_external_account(*, actor, secret='', event_id=None, source_service='manager_api', **data):
    event_id = _event_uuid(event_id)
    existing_event = ActivityLog.objects.filter(event_id=event_id).first()
    if existing_event:
        if existing_event.action != 'EXTERNAL_ACCOUNT_CREATED':
            raise ExternalAccountError('event_id уже использован для другого события.')
        return ExternalAccount.objects.get(public_id=existing_event.object_id), False

    student = data['student']
    application = data.get('application')
    _validate_application(student, application)
    data.setdefault('responsible', actor)
    data.setdefault('created_by', actor)
    account = ExternalAccount(**data)
    account.full_clean(exclude=['secret_ciphertext', 'secret_updated_at'])
    if secret:
        account.secret_ciphertext = encrypt_external_secret(secret)
        account.secret_updated_at = timezone.now()
    account.save()
    ActivityLog.objects.create(
        event_id=event_id,
        actor=actor,
        service=source_service,
        student=student,
        application=application,
        object_type='crm.ExternalAccount',
        object_id=str(account.public_id),
        action='EXTERNAL_ACCOUNT_CREATED',
        new_data={
            'system': account.system, 'provider_name': account.provider_name,
            'status': account.status, 'has_secret': account.has_secret,
        },
    )
    return account, True


@transaction.atomic
def update_external_account(account, *, actor, secret=None, event_id=None, source_service='manager_api', **changes):
    event_id = _event_uuid(event_id)
    existing_event = ActivityLog.objects.filter(event_id=event_id).first()
    if existing_event:
        if existing_event.object_id != str(account.public_id):
            raise ExternalAccountError('event_id уже использован для другого объекта.')
        return ExternalAccount.objects.get(pk=account.pk), False

    # Lock only the account row. PostgreSQL rejects FOR UPDATE when Django's
    # select_related() adds the nullable application as an outer join.
    locked = ExternalAccount.objects.select_for_update().get(pk=account.pk)
    immutable_fields = {'student', 'application', 'system'}
    for field in immutable_fields:
        if field in changes and changes[field] != getattr(locked, field):
            raise ExternalAccountError('Студента, заявку и тип системы нельзя менять после создания.')
    old_data = {
        field: str(getattr(locked, field) or '')
        for field in ('provider_name', 'portal_url', 'email', 'login', 'status', 'issue', 'notes', 'last_checked_at')
    }
    for field, value in changes.items():
        if field not in immutable_fields and hasattr(locked, field):
            setattr(locked, field, value)
    secret_rotated = secret is not None
    if secret_rotated:
        locked.secret_ciphertext = encrypt_external_secret(secret)
        locked.secret_updated_at = timezone.now() if secret else None
    locked.full_clean(exclude=['secret_ciphertext', 'secret_updated_at'])
    locked.save()
    new_data = {
        field: str(getattr(locked, field) or '')
        for field in ('provider_name', 'portal_url', 'email', 'login', 'status', 'issue', 'notes', 'last_checked_at')
    }
    new_data['has_secret'] = locked.has_secret
    ActivityLog.objects.create(
        event_id=event_id,
        actor=actor,
        service=source_service,
        student=locked.student,
        application=locked.application,
        object_type='crm.ExternalAccount',
        object_id=str(locked.public_id),
        action='EXTERNAL_ACCOUNT_SECRET_ROTATED' if secret_rotated else 'EXTERNAL_ACCOUNT_UPDATED',
        old_data=old_data,
        new_data=new_data,
    )
    return locked, True
