"""Canonical, idempotent exam writes used by ManagerSL and ExamSL."""

from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from .credentials import encrypt_external_secret
from .models import ActivityLog, Application, ApplicationExam, ApplicationExamEvent
from .workflow import STAGE_RANK, TERMINAL_STAGES, transition_application


class ExamRegistryError(ValueError):
    pass


def _uuid(value):
    if value in (None, ''):
        return uuid4()
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ExamRegistryError('event_id должен быть UUID.') from exc


def _snapshot(exam):
    return {
        'application_public_id': str(exam.application.public_id),
        'student_public_id': str(exam.student.public_id),
        'student_sl_id': exam.student.sl_id,
        'subject': exam.subject,
        'scheduled_at': exam.scheduled_at.isoformat(),
        'timezone': exam.timezone,
        'status': exam.status,
        'result': exam.result,
        'score': exam.score,
        'retake_at': exam.retake_at.isoformat() if exam.retake_at else None,
        'has_secret': exam.has_secret,
        'source_version': exam.source_version,
    }


@transaction.atomic
def upsert_application_exam(*, application, subject, scheduled_at, source_service, source_id,
                            actor=None, event_id=None, secret=None, **values):
    event_id = _uuid(event_id)
    existing_event = ApplicationExamEvent.objects.select_related('exam').filter(event_id=event_id).first()
    if existing_event:
        exam = existing_event.exam
        if exam.source_service != source_service or exam.source_id != source_id:
            raise ExamRegistryError('event_id уже использован для другого экзамена.')
        return exam, False

    if not source_service or not source_id:
        raise ExamRegistryError('source_service и source_id обязательны.')
    if application.client_id is None:
        raise ExamRegistryError('У заявки нет студента.')

    exam = ApplicationExam.objects.select_for_update().filter(
        source_service=source_service, source_id=source_id,
    ).first()
    created = exam is None
    if exam and exam.application_id != application.pk:
        raise ExamRegistryError('Идентификатор источника уже связан с другой заявкой.')
    old_data = _snapshot(exam) if exam else {}
    if exam is None:
        exam = ApplicationExam(
            application=application,
            student=application.client,
            source_service=source_service,
            source_id=source_id,
            created_by=actor,
        )

    allowed = {
        'timezone', 'join_url', 'login', 'status', 'result', 'score', 'retake_at',
        'comment', 'responsible', 'source_version', 'client_acknowledged_at',
    }
    exam.subject = str(subject or '').strip()[:255]
    if not exam.subject:
        raise ExamRegistryError('Название экзамена обязательно.')
    exam.scheduled_at = scheduled_at
    for field, value in values.items():
        if field in allowed:
            setattr(exam, field, value)
    if secret is not None:
        exam.secret_ciphertext = encrypt_external_secret(str(secret)) if secret else ''
    try:
        exam.full_clean()
    except ValidationError as exc:
        raise ExamRegistryError(str(exc)) from exc
    exam.save()

    new_data = _snapshot(exam)
    action = 'EXAM_CREATED' if created else 'EXAM_UPDATED'
    ApplicationExamEvent.objects.create(
        event_id=event_id, exam=exam, action=action, actor=actor,
        source_service=source_service, old_data=old_data, new_data=new_data,
    )
    ActivityLog.objects.create(
        actor=actor, service=source_service, student=exam.student, application=application,
        object_type='crm.ApplicationExam', object_id=str(exam.public_id), action=action,
        old_data=old_data, new_data=new_data, metadata={'event_id': str(event_id)},
    )

    current_rank = STAGE_RANK.get(application.current_stage, -1)
    exam_rank = STAGE_RANK.get(Application.STAGE_EXAM_SCHEDULED, -1)
    if created and application.current_stage not in TERMINAL_STAGES and current_rank < exam_rank:
        transition_application(
            application, Application.STAGE_EXAM_SCHEDULED, actor=actor,
            source_service=source_service, event_id=uuid4(),
            comment=f'Назначен экзамен: {exam.subject}',
        )
    return exam, created


@transaction.atomic
def acknowledge_application_exam(exam, *, acknowledged_at, source_service, event_id=None):
    event_id = _uuid(event_id)
    existing = ApplicationExamEvent.objects.filter(event_id=event_id).first()
    if existing:
        if existing.exam_id != exam.pk:
            raise ExamRegistryError('event_id уже использован для другого экзамена.')
        return existing.exam, False
    locked = ApplicationExam.objects.select_for_update().get(pk=exam.pk)
    old_data = _snapshot(locked)
    locked.client_acknowledged_at = acknowledged_at
    locked.save(update_fields=['client_acknowledged_at', 'updated_at'])
    new_data = _snapshot(locked)
    ApplicationExamEvent.objects.create(
        event_id=event_id, exam=locked, action='EXAM_ACKNOWLEDGED',
        source_service=source_service, old_data=old_data, new_data=new_data,
    )
    ActivityLog.objects.create(
        service=source_service, student=locked.student, application=locked.application,
        object_type='crm.ApplicationExam', object_id=str(locked.public_id),
        action='EXAM_ACKNOWLEDGED', old_data=old_data, new_data=new_data,
        metadata={'event_id': str(event_id)},
    )
    return locked, True
