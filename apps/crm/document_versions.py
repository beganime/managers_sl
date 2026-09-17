"""Canonical document upload versions and append-only review decisions."""

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ActivityLog, ClientFile, ClientFileReviewEvent, ClientFileVersion


class DocumentVersionError(ValueError):
    pass


@transaction.atomic
def record_document_version(
    document,
    *,
    original_name,
    storage_path,
    folder_url='',
    mime_type='',
    size_bytes=0,
    sha256='',
    application=None,
    uploaded_by=None,
    uploader_data=None,
    source_service='manager_sl',
    event_id=None,
):
    event_id = event_id or uuid4()
    existing = ClientFileVersion.objects.filter(event_id=event_id).first()
    if existing:
        if existing.document_id != document.pk:
            raise DocumentVersionError('Upload event already belongs to another document.')
        return existing, False

    locked = ClientFile.objects.select_for_update().get(pk=document.pk)
    application = application or locked.application
    if application and application.client_id != locked.client_id:
        raise DocumentVersionError('Document application must belong to the same student.')
    version_number = locked.current_version_number + 1
    version = ClientFileVersion(
        event_id=event_id,
        document=locked,
        application=application,
        version_number=version_number,
        original_name=str(original_name or '')[:255],
        storage_path=str(storage_path or '')[:1000],
        folder_url=str(folder_url or '')[:1000],
        mime_type=str(mime_type or '')[:100],
        size_bytes=max(int(size_bytes or 0), 0),
        sha256=str(sha256 or '')[:64],
        source_service=str(source_service or 'manager_sl')[:80],
        uploaded_by=uploaded_by,
        uploader_data=uploader_data or {},
    )
    try:
        version.full_clean()
    except ValidationError as exc:
        raise DocumentVersionError(str(exc)) from exc
    version.save()

    locked.current_version_number = version_number
    locked.application = application
    locked.status = ClientFile.STATUS_PENDING
    locked.review_comment = ''
    locked.reviewed_at = None
    locked.reviewed_by = None
    locked.save(update_fields=[
        'current_version_number', 'application', 'status', 'review_comment',
        'reviewed_at', 'reviewed_by', 'updated_at',
    ])
    ActivityLog.objects.create(
        event_id=event_id,
        actor=uploaded_by,
        service=source_service,
        student=locked.client,
        application=application,
        object_type='ClientFileVersion',
        object_id=str(version.public_id),
        action='DOCUMENT_VERSION_UPLOADED',
        new_data={
            'document_id': locked.pk,
            'version': version_number,
            'original_name': version.original_name,
            'mime_type': version.mime_type,
            'size_bytes': version.size_bytes,
            'sha256': version.sha256,
        },
    )
    return version, True


@transaction.atomic
def record_document_review(
    document,
    *,
    status,
    comment='',
    reviewer=None,
    reviewer_data=None,
    source_service='manager_sl',
    event_id=None,
):
    if status not in {ClientFile.STATUS_PENDING, ClientFile.STATUS_APPROVED, ClientFile.STATUS_REJECTED}:
        raise DocumentVersionError('Invalid document review status.')
    event_id = event_id or uuid4()
    existing = ClientFileReviewEvent.objects.filter(event_id=event_id).first()
    if existing:
        if existing.document_id != document.pk:
            raise DocumentVersionError('Review event already belongs to another document.')
        return existing, False

    locked = ClientFile.objects.select_for_update().get(pk=document.pk)
    version = locked.versions.order_by('-version_number').first()
    if not version:
        raise DocumentVersionError('Document does not have an uploaded version.')
    review = ClientFileReviewEvent(
        event_id=event_id,
        document=locked,
        version=version,
        status=status,
        comment=str(comment or '')[:1000],
        reviewer=reviewer,
        reviewer_data=reviewer_data or {},
        source_service=str(source_service or 'manager_sl')[:80],
    )
    try:
        review.full_clean()
    except ValidationError as exc:
        raise DocumentVersionError(str(exc)) from exc
    review.save()

    locked.status = status
    locked.review_comment = review.comment
    locked.reviewed_at = review.created_at
    locked.reviewed_by = reviewer
    locked.external_review_data = review.reviewer_data
    locked.save(update_fields=[
        'status', 'review_comment', 'reviewed_at', 'reviewed_by',
        'external_review_data', 'updated_at',
    ])
    ActivityLog.objects.create(
        event_id=event_id,
        actor=reviewer,
        service=source_service,
        student=locked.client,
        application=version.application,
        object_type='ClientFileVersion',
        object_id=str(version.public_id),
        action='DOCUMENT_VERSION_REVIEWED',
        old_data={'status': ClientFile.STATUS_PENDING},
        new_data={'status': status, 'comment': review.comment, 'version': version.version_number},
    )
    return review, True
