"""Canonical, idempotent translation records received from TranslateSL."""

from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ActivityLog, TranslationEvent, TranslationRecord


class TranslationRegistryError(ValueError):
    pass


def _uuid(value):
    if value in (None, ''):
        return uuid4()
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise TranslationRegistryError('event_id должен быть UUID.') from exc


def _snapshot(record):
    return {
        'student_public_id': str(record.student.public_id) if record.student_id else None,
        'application_public_id': str(record.application.public_id) if record.application_id else None,
        'document_version_public_id': (
            str(record.source_document_version.public_id) if record.source_document_version_id else None
        ),
        'title': record.title,
        'source_language': record.source_language,
        'target_language': record.target_language,
        'template_name': record.template_name,
        'version': record.version,
        'status': record.status,
        'source_storage_path': record.source_storage_path,
        'result_storage_path': record.result_storage_path,
        'source_version': record.source_version,
    }


@transaction.atomic
def upsert_translation(*, source_service, source_id, event_id, title, status,
                       student=None, application=None, source_document_version=None,
                       actor=None, **values):
    event_id = _uuid(event_id)
    replay = TranslationEvent.objects.select_related('translation').filter(event_id=event_id).first()
    if replay:
        record = replay.translation
        if record.source_service != source_service or record.source_id != source_id:
            raise TranslationRegistryError('event_id уже использован для другого перевода.')
        return record, False
    if not source_service or not source_id:
        raise TranslationRegistryError('source_service и source_id обязательны.')

    record = TranslationRecord.objects.select_for_update().filter(
        source_service=source_service, source_id=source_id,
    ).first()
    created = record is None
    if record is None:
        record = TranslationRecord(source_service=source_service, source_id=source_id)
    else:
        incoming_version = int(values.get('source_version') or 1)
        if incoming_version < record.source_version:
            raise TranslationRegistryError('Получена устаревшая версия перевода.')
        bindings = (
            ('student', record.student_id, getattr(student, 'pk', None)),
            ('application', record.application_id, getattr(application, 'pk', None)),
            ('source_document_version', record.source_document_version_id, getattr(source_document_version, 'pk', None)),
        )
        for field, current_id, incoming_id in bindings:
            if current_id is not None and incoming_id != current_id:
                raise TranslationRegistryError(f'Источник уже связан с другим объектом: {field}.')
    old_data = _snapshot(record) if record.pk else {}
    record.student = student
    record.application = application
    record.source_document_version = source_document_version
    record.title = str(title or '').strip()[:255]
    record.status = status
    allowed = {
        'source_language', 'target_language', 'template_name', 'version',
        'source_storage_path', 'result_storage_path', 'translator', 'reviewer', 'source_version',
    }
    for field, value in values.items():
        if field in allowed:
            setattr(record, field, value)
    if not record.title:
        raise TranslationRegistryError('Название перевода обязательно.')
    try:
        record.full_clean()
    except ValidationError as exc:
        raise TranslationRegistryError(str(exc)) from exc
    record.save()

    new_data = _snapshot(record)
    action = 'TRANSLATION_CREATED' if created else 'TRANSLATION_UPDATED'
    TranslationEvent.objects.create(
        event_id=event_id, translation=record, action=action, actor=actor,
        source_service=source_service, old_data=old_data, new_data=new_data,
    )
    # ActivityLog is intentionally student-scoped. Independent translations
    # remain auditable through TranslationEvent without inventing a student.
    if student is not None:
        ActivityLog.objects.create(
            actor=actor, service=source_service, student=student, application=application,
            object_type='crm.TranslationRecord', object_id=str(record.public_id), action=action,
            old_data=old_data, new_data=new_data, metadata={'event_id': str(event_id)},
        )
    return record, created
