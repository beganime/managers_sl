"""Canonical admission stage transitions and immutable audit records."""

from uuid import UUID, uuid4

from django.db import transaction

from .models import ActivityLog, Application, ApplicationStageHistory


class WorkflowTransitionError(ValueError):
    pass


STAGE_ORDER = [value for value, _label in Application.STAGE_CHOICES if value not in {
    Application.STAGE_REJECTED,
    Application.STAGE_CANCELLED,
    Application.STAGE_ON_HOLD,
}]
STAGE_RANK = {stage: rank for rank, stage in enumerate(STAGE_ORDER)}
TERMINAL_STAGES = {
    Application.STAGE_ENROLLED,
    Application.STAGE_REJECTED,
    Application.STAGE_CANCELLED,
}


def _event_uuid(value):
    if value in (None, ''):
        return uuid4()
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise WorkflowTransitionError('event_id должен быть UUID.') from exc


def _validate_transition(old_stage, new_stage, comment):
    valid = {value for value, _label in Application.STAGE_CHOICES}
    if new_stage not in valid:
        raise WorkflowTransitionError('Неизвестный этап поступления.')
    if old_stage == new_stage:
        return
    if old_stage in TERMINAL_STAGES:
        raise WorkflowTransitionError('Завершённую заявку нельзя перевести на другой этап.')
    if new_stage in {Application.STAGE_REJECTED, Application.STAGE_CANCELLED, Application.STAGE_ON_HOLD}:
        if not comment.strip():
            raise WorkflowTransitionError('Для отказа, отмены или паузы укажите комментарий.')
        return
    if old_stage == Application.STAGE_ON_HOLD:
        if not comment.strip():
            raise WorkflowTransitionError('Для возобновления заявки укажите комментарий.')
        return
    if old_stage == Application.STAGE_EXAM_FAILED and new_stage == Application.STAGE_EXAM_SCHEDULED:
        return
    if STAGE_RANK.get(new_stage, -1) <= STAGE_RANK.get(old_stage, -1):
        raise WorkflowTransitionError('Возврат на предыдущий этап требует отдельной корректирующей операции.')


@transaction.atomic
def record_application_created(application, *, actor=None, source_service='manager_sl', event_id=None, comment=''):
    event_id = _event_uuid(event_id)
    existing = ApplicationStageHistory.objects.filter(event_id=event_id).first()
    if existing:
        if existing.application_id != application.pk or existing.new_stage != application.current_stage:
            raise WorkflowTransitionError('event_id уже использован для другого события.')
        return existing, False

    history = ApplicationStageHistory.objects.create(
        event_id=event_id,
        application=application,
        old_stage='',
        new_stage=application.current_stage,
        actor=actor,
        source_service=source_service,
        comment=comment,
    )
    ActivityLog.objects.create(
        event_id=event_id,
        actor=actor,
        service=source_service,
        student=application.client,
        application=application,
        object_type='crm.Application',
        object_id=str(application.public_id or application.pk),
        action='APPLICATION_CREATED',
        new_data={'current_stage': application.current_stage},
    )
    return history, True


@transaction.atomic
def transition_application(application, new_stage, *, actor=None, source_service='manager_sl', comment='', event_id=None):
    event_id = _event_uuid(event_id)
    existing = ApplicationStageHistory.objects.select_related('application').filter(event_id=event_id).first()
    if existing:
        if existing.application_id != application.pk or existing.new_stage != new_stage:
            raise WorkflowTransitionError('event_id уже использован для другого перехода.')
        return existing.application, existing, False

    locked = Application.objects.select_for_update().select_related('client').get(pk=application.pk)
    old_stage = locked.current_stage
    _validate_transition(old_stage, new_stage, comment)
    if old_stage == new_stage:
        return locked, None, False

    locked.current_stage = new_stage
    locked.save(update_fields=['current_stage', 'updated_at'])
    history = ApplicationStageHistory.objects.create(
        event_id=event_id,
        application=locked,
        old_stage=old_stage,
        new_stage=new_stage,
        actor=actor,
        source_service=source_service,
        comment=comment.strip(),
    )
    ActivityLog.objects.create(
        event_id=event_id,
        actor=actor,
        service=source_service,
        student=locked.client,
        application=locked,
        object_type='crm.Application',
        object_id=str(locked.public_id or locked.pk),
        action='APPLICATION_STAGE_CHANGED',
        old_data={'current_stage': old_stage},
        new_data={'current_stage': new_stage},
        metadata={'comment': comment.strip()},
    )
    return locked, history, True
