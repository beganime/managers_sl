"""Idempotent SMTP_SL -> ManagerSL mail metadata registry."""

from __future__ import annotations

from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import Q

from apps.client_onboarding.models import ClientServiceIdentity

from .models import ActivityLog, Application, Client, EmailRecord, ExternalAccount


class EmailRegistryError(ValueError):
    pass


def _uuid(value, field_name):
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise EmailRegistryError(f'{field_name} должен быть UUID.') from exc


def _resolve_student(payload):
    public_id = str(payload.get('student_public_id') or '').strip()
    sl_id = str(payload.get('sl_id') or '').strip()
    mailbox = str(payload.get('mailbox') or '').strip().casefold()
    if public_id:
        student = Client.objects.filter(public_id=_uuid(public_id, 'student_public_id')).first()
        if student is None:
            raise EmailRegistryError('Клиент по UUID не найден.')
        return student
    if sl_id:
        student = Client.objects.filter(sl_id__iexact=sl_id).first()
        if student is None:
            raise EmailRegistryError('Клиент по SL-ID не найден.')
        return student
    if not mailbox:
        return None

    identity = ClientServiceIdentity.objects.select_related('client').filter(
        tmmail_email__iexact=mailbox,
    ).first()
    if identity:
        return identity.client
    matches = list(Client.objects.filter(
        Q(email__iexact=mailbox)
        | Q(external_accounts__system=ExternalAccount.SYSTEM_EMAIL, external_accounts__email__iexact=mailbox)
    ).distinct()[:2])
    return matches[0] if len(matches) == 1 else None


def _resolve_application(payload, student):
    value = str(payload.get('application_public_id') or '').strip()
    if value:
        application = Application.objects.filter(public_id=_uuid(value, 'application_public_id')).first()
        if application is None:
            raise EmailRegistryError('Заявка в университет не найдена.')
        if student and application.client_id != student.pk:
            raise EmailRegistryError('Заявка принадлежит другому клиенту.')
        return application, student or application.client

    university = str(payload.get('university_name') or '').strip()
    if not student or not university:
        return None, student
    candidates = list(Application.objects.filter(client=student).filter(
        Q(university_name__iexact=university)
        | Q(university__name__iexact=university)
        | Q(university__abbreviation__iexact=university)
    )[:2])
    return (candidates[0], student) if len(candidates) == 1 else (None, student)


@transaction.atomic
def upsert_email_record(payload):
    source_id = str(payload.get('source_id') or '').strip()
    if not source_id or len(source_id) > 160:
        raise EmailRegistryError('source_id обязателен и не длиннее 160 символов.')
    source_service = str(payload.get('source_service') or 'smtp_sl').strip()[:80]
    source_version = int(payload.get('source_version') or 1)
    if source_version < 1:
        raise EmailRegistryError('source_version должен быть положительным числом.')

    student = _resolve_student(payload)
    application, student = _resolve_application(payload, student)
    defaults = {
        'student': student,
        'application': application,
        'responsible': student.manager if student else None,
        'mailbox': str(payload.get('mailbox') or '').strip().casefold()[:254],
        'sender_email': str(payload.get('sender_email') or '').strip().casefold()[:254],
        'sender_name': str(payload.get('sender_name') or '').strip()[:255],
        'recipient_email': str(payload.get('recipient_email') or '').strip().casefold()[:254],
        'subject': str(payload.get('subject') or '')[:500],
        'received_at': payload['received_at'],
        'category': str(payload.get('category') or 'primary')[:20],
        'importance': str(payload.get('importance') or 'normal')[:20],
        'university_name': str(payload.get('university_name') or '')[:255],
        'attachment_count': max(0, int(payload.get('attachment_count') or 0)),
        'body_preview': str(payload.get('body_preview') or '')[:1000],
        'source_url': str(payload.get('source_url') or '')[:1000],
        'is_read': bool(payload.get('is_read', False)),
        'is_replied': bool(payload.get('is_replied', False)),
        'processed': bool(payload.get('processed', False)),
        'source_version': source_version,
    }
    if not defaults['mailbox'] or not defaults['sender_email'] or not defaults['recipient_email']:
        raise EmailRegistryError('mailbox, sender_email и recipient_email обязательны.')

    existing = EmailRecord.objects.select_for_update().filter(
        source_service=source_service, source_id=source_id,
    ).first()
    created = existing is None
    if existing and source_version < existing.source_version:
        return existing, False, False
    old_data = {}
    if existing:
        if existing.student_id and student and existing.student_id != student.pk:
            raise EmailRegistryError('Письмо уже связано с другим клиентом; перепривязка источником запрещена.')
        if existing.student_id and student is None:
            student = existing.student
            defaults['student'] = student
            defaults['application'] = existing.application
            defaults['responsible'] = student.manager
        old_data = {
            'student_id': existing.student_id, 'application_id': existing.application_id,
            'processed': existing.processed, 'is_read': existing.is_read,
            'is_replied': existing.is_replied, 'source_version': existing.source_version,
        }
        for field, value in defaults.items():
            setattr(existing, field, value)
        existing.full_clean()
        existing.save()
        record = existing
    else:
        record = EmailRecord(source_service=source_service, source_id=source_id, **defaults)
        record.full_clean()
        record.save()

    changed = created or any(old_data.get(field) != getattr(record, field) for field in old_data)
    if student and changed:
        ActivityLog.objects.create(
            event_id=(_uuid(payload.get('event_id'), 'event_id') or uuid4()) if created else uuid4(),
            service=source_service,
            student=student,
            application=application,
            object_type='crm.EmailRecord',
            object_id=str(record.public_id),
            action='email_received' if created else 'email_updated',
            old_data=old_data,
            new_data={
                'subject': record.subject, 'mailbox': record.mailbox,
                'processed': record.processed, 'is_read': record.is_read,
                'is_replied': record.is_replied, 'source_version': record.source_version,
            },
            metadata={'source_url': record.source_url},
        )
    return record, created, changed
