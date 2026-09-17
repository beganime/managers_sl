"""Bounded read model for the canonical Student 360 screen and API.

The snapshot composes existing domain records. It deliberately does not copy
them into another table, so it cannot become a second source of truth.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.core.permissions import filter_manager_owned
from apps.erp_documents.models import GeneratedDocument
from apps.finance.models import Deal

from .models import (
    ActivityLog, Application, ApplicationExam, ApplicationStageHistory, ClientActivity, ClientFile,
    ClientFileReviewEvent, ClientFileVersion, ClientNote, EmailRecord, ExternalAccount, TranslationRecord,
)


DEFAULT_SECTION_LIMIT = 100


def _iso(value):
    if not value:
        return None
    if hasattr(value, 'utcoffset') and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.isoformat()


def _user_name(user):
    if not user:
        return None
    return user.get_full_name().strip() or getattr(user, 'email', '') or str(user)


def _catalog_name(reference, legacy_value):
    if reference:
        return getattr(reference, 'abbreviation', '') or getattr(reference, 'name', '') or str(reference)
    return legacy_value or ''


def build_student_360(client, *, user, include_sensitive=False, limit=DEFAULT_SECTION_LIMIT):
    """Return a JSON-safe view of one client already authorized by the caller."""
    applications = list(
        Application.objects.filter(client=client)
        .select_related('university', 'program', 'country_reference', 'manager', 'office')
        .order_by('-created_at')[:limit]
    )
    stage_history = defaultdict(list)
    for event in (
        ApplicationStageHistory.objects.filter(application__client=client)
        .select_related('actor')
        .order_by('-created_at')[:limit]
    ):
        stage_history[event.application_id].append(event)
    files = list(
        ClientFile.objects.filter(client=client)
        .select_related('application', 'uploaded_by', 'reviewed_by')
        .prefetch_related(
            Prefetch(
                'versions',
                queryset=ClientFileVersion.objects.select_related('application', 'uploaded_by')
                    .prefetch_related(Prefetch(
                        'review_events',
                        queryset=ClientFileReviewEvent.objects.select_related('reviewer').order_by('-created_at'),
                    ))
                    .order_by('-version_number'),
            )
        )
        .order_by('-created_at')[:limit]
    ) if include_sensitive else []
    generated_documents_query = GeneratedDocument.objects.filter(client=client).select_related(
        'application', 'template', 'manager', 'approved_by'
    )
    generated_documents = list(
        filter_manager_owned(generated_documents_query, user, manager_field='manager')
        .order_by('-created_at')[:limit]
    ) if include_sensitive else []
    deal_query = Deal.objects.filter(client=client).select_related(
        'application', 'manager', 'office', 'currency'
    ).prefetch_related('payments__currency', 'payments__manager')
    deals = list(
        filter_manager_owned(deal_query, user, manager_field='manager').order_by('-created_at')[:limit]
    )
    activities = list(
        ClientActivity.objects.filter(client=client)
        .select_related('manager')
        .order_by('-created_at')[:limit]
    )
    notes_query = ClientNote.objects.filter(client=client).select_related('author')
    if not getattr(user, 'is_staff', False) and not getattr(user, 'is_superuser', False):
        notes_query = notes_query.filter(Q(is_private=False) | Q(author=user))
    notes = list(notes_query.order_by('-created_at')[:limit])
    canonical_events = list(
        ActivityLog.objects.filter(student=client)
        .select_related('actor', 'application')
        .order_by('-created_at')[:limit]
    )
    external_accounts = list(
        ExternalAccount.objects.filter(student=client)
        .select_related('application', 'responsible')
        .order_by('-created_at')[:limit]
    )
    exams = list(
        ApplicationExam.objects.filter(student=client)
        .select_related('application', 'application__university', 'application__program', 'responsible')
        .order_by('-scheduled_at')[:limit]
    )
    translations = list(
        TranslationRecord.objects.filter(student=client)
        .select_related('application', 'source_document_version', 'translator', 'reviewer')
        .order_by('-created_at')[:limit]
    )
    emails = list(
        EmailRecord.objects.filter(student=client)
        .select_related('application', 'responsible')
        .order_by('-received_at')[:limit]
    )

    timeline = []
    for item in canonical_events:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'canonical_event',
            'title': item.action, 'detail': (item.metadata or {}).get('comment', ''),
            'actor': _user_name(item.actor), 'object_id': str(item.event_id),
        })
    for item in activities:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'activity', 'title': item.title,
            'detail': item.description, 'actor': _user_name(item.manager), 'object_id': str(item.pk),
        })
    for item in notes:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'note',
            'title': 'Приватная заметка' if item.is_private else 'Заметка',
            'detail': item.text, 'actor': _user_name(item.author), 'object_id': str(item.pk),
        })
    for item in applications:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'application', 'title': 'Создана заявка в вуз',
            'detail': ' / '.join(filter(None, [
                _catalog_name(item.university, item.university_name),
                _catalog_name(item.program, item.program_name),
            ])),
            'actor': _user_name(item.manager), 'object_id': str(item.public_id or item.pk),
        })
    for item in exams:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'exam', 'title': item.subject,
            'detail': f'{item.get_status_display()} · {_iso(item.scheduled_at)}',
            'actor': _user_name(item.responsible), 'object_id': str(item.public_id),
        })
    for item in translations:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'translation', 'title': item.title,
            'detail': item.get_status_display(), 'actor': _user_name(item.translator),
            'object_id': str(item.public_id),
        })
    for item in emails:
        timeline.append({
            'at': _iso(item.received_at), 'kind': 'email',
            'title': item.subject or 'Письмо без темы',
            'detail': item.sender_email, 'actor': _user_name(item.responsible),
            'object_id': str(item.public_id),
        })
    for item in files:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'file', 'title': item.title,
            'detail': item.get_status_display(), 'actor': _user_name(item.uploaded_by),
            'object_id': str(item.pk),
        })
    for item in generated_documents:
        timeline.append({
            'at': _iso(item.created_at), 'kind': 'generated_document', 'title': item.display_title,
            'detail': item.get_status_display(), 'actor': _user_name(item.manager),
            'object_id': str(item.pk),
        })
    for deal in deals:
        for payment in deal.payments.all():
            timeline.append({
                'at': _iso(payment.created_at), 'kind': 'payment',
                'title': f'Платёж по договору {deal.contract_number or deal.title}',
                'detail': f'{payment.amount} {payment.currency.code}',
                'actor': _user_name(payment.manager), 'object_id': str(payment.pk),
            })
    timeline.sort(key=lambda row: row['at'] or '', reverse=True)

    student = {
        'public_id': str(client.public_id) if client.public_id else None,
        'sl_id': client.sl_id, 'full_name': client.full_name,
        'date_of_birth': _iso(client.dob), 'citizenship': client.citizenship,
        'phone': client.phone, 'email': client.email,
        'office': client.office.name if client.office_id else None,
        'manager': _user_name(client.manager),
        'lead_source': client.lead_source.name if client.lead_source_id else None,
        'status': client.status, 'status_display': client.get_status_display(),
        'academic_year': client.academic_year, 'created_at': _iso(client.created_at),
    }
    if include_sensitive:
        student.update({
            'passport_local_num': client.passport_local_num,
            'passport_inter_num': client.passport_inter_num,
            'address': client.address,
            'address_registration': client.address_registration,
        })

    return {
        'student': student,
        'applications': [{
            'public_id': str(item.public_id) if item.public_id else None,
            'university': _catalog_name(item.university, item.university_name),
            'program': _catalog_name(item.program, item.program_name),
            'country': _catalog_name(item.country_reference, item.country),
            'academic_year': item.academic_year, 'degree': item.degree, 'language': item.language,
            'intake': item.intake, 'status': item.status, 'status_display': item.get_status_display(),
            'current_stage': item.current_stage, 'current_stage_display': item.get_current_stage_display(),
            'funding_type': item.funding_type, 'deadline': _iso(item.deadline),
            'admission_result': item.admission_result,
            'manager': _user_name(item.manager), 'created_at': _iso(item.created_at),
            'stage_history': [{
                'event_id': str(event.event_id), 'old_stage': event.old_stage,
                'new_stage': event.new_stage, 'source_service': event.source_service,
                'comment': event.comment, 'created_at': _iso(event.created_at),
            } for event in stage_history[item.pk]],
        } for item in applications],
        'documents': [{
            'id': item.pk,
            'application_public_id': str(item.application.public_id) if item.application_id else None,
            'title': item.title, 'type': item.file_type, 'status': item.status,
            'status_display': item.get_status_display(), 'version': item.current_version_number,
            'review_comment': item.review_comment, 'uploaded_by': _user_name(item.uploaded_by),
            'reviewed_by': _user_name(item.reviewed_by), 'reviewed_at': _iso(item.reviewed_at),
            'created_at': _iso(item.created_at),
            'versions': [{
                'public_id': str(version.public_id),
                'version': version.version_number,
                'application_public_id': (
                    str(version.application.public_id) if version.application_id else None
                ),
                'original_name': version.original_name,
                'storage_path': version.storage_path,
                'folder_url': version.folder_url,
                'mime_type': version.mime_type,
                'size_bytes': version.size_bytes,
                'sha256': version.sha256,
                'uploaded_by': _user_name(version.uploaded_by),
                'created_at': _iso(version.created_at),
                'reviews': [{
                    'event_id': str(review.event_id),
                    'status': review.status,
                    'comment': review.comment,
                    'reviewer': _user_name(review.reviewer)
                        or (review.reviewer_data or {}).get('reviewed_by_display', ''),
                    'created_at': _iso(review.created_at),
                } for review in version.review_events.all()[:limit]],
            } for version in item.versions.all()[:limit]],
        } for item in files],
        'generated_documents': [{
            'id': item.pk,
            'application_public_id': str(item.application.public_id) if item.application_id else None,
            'title': item.display_title, 'template': item.template.name, 'status': item.status,
            'status_display': item.get_status_display(), 'created_at': _iso(item.created_at),
        } for item in generated_documents],
        'contracts': [{
            'id': item.pk,
            'application_public_id': str(item.application.public_id) if item.application_id else None,
            'number': item.contract_number, 'title': item.title, 'status': item.payment_status,
            'status_display': item.get_payment_status_display(), 'total_usd': str(item.total_to_pay_usd),
            'paid_usd': str(item.paid_amount_usd), 'remaining_usd': str(item.remaining_amount_usd),
            'created_at': _iso(item.created_at),
        } for item in deals],
        'external_accounts': [{
            'public_id': str(item.public_id),
            'application_public_id': str(item.application.public_id) if item.application_id else None,
            'system': item.system, 'system_display': item.get_system_display(),
            'provider_name': item.provider_name, 'portal_url': item.portal_url,
            'email': item.email, 'login': item.login, 'has_secret': item.has_secret,
            'status': item.status, 'status_display': item.get_status_display(),
            'last_checked_at': _iso(item.last_checked_at), 'issue': item.issue,
            'responsible': _user_name(item.responsible), 'notes': item.notes,
            'created_at': _iso(item.created_at),
        } for item in external_accounts],
        'exams': [{
            'public_id': str(item.public_id),
            'application_public_id': str(item.application.public_id),
            'university': _catalog_name(item.application.university, item.application.university_name),
            'program': _catalog_name(item.application.program, item.application.program_name),
            'subject': item.subject, 'scheduled_at': _iso(item.scheduled_at),
            'timezone': item.timezone, 'status': item.status,
            'status_display': item.get_status_display(), 'result': item.result,
            'score': item.score, 'retake_at': _iso(item.retake_at),
            'responsible': _user_name(item.responsible),
            'client_acknowledged_at': _iso(item.client_acknowledged_at),
            'created_at': _iso(item.created_at),
        } for item in exams],
        'translations': [{
            'public_id': str(item.public_id),
            'application_public_id': str(item.application.public_id) if item.application_id else None,
            'document_version_public_id': (
                str(item.source_document_version.public_id) if item.source_document_version_id else None
            ),
            'title': item.title, 'source_language': item.source_language,
            'target_language': item.target_language, 'template_name': item.template_name,
            'version': item.version, 'status': item.status,
            'status_display': item.get_status_display(),
            'source_storage_path': item.source_storage_path,
            'result_storage_path': item.result_storage_path,
            'translator': _user_name(item.translator), 'reviewer': _user_name(item.reviewer),
            'created_at': _iso(item.created_at), 'updated_at': _iso(item.updated_at),
        } for item in translations],
        'emails': [{
            'public_id': str(item.public_id),
            'application_public_id': str(item.application.public_id) if item.application_id else None,
            'mailbox': item.mailbox, 'sender_email': item.sender_email,
            'sender_name': item.sender_name, 'recipient_email': item.recipient_email,
            'subject': item.subject, 'received_at': _iso(item.received_at),
            'category': item.category, 'importance': item.importance,
            'university_name': item.university_name,
            'attachment_count': item.attachment_count, 'body_preview': item.body_preview if include_sensitive else '',
            'source_url': item.source_url, 'is_read': item.is_read,
            'is_replied': item.is_replied, 'processed': item.processed,
            'responsible': _user_name(item.responsible),
        } for item in emails],
        'timeline': timeline[:limit],
        'capabilities': {
            'activity_log': True, 'admission_stage_history': True,
            'document_versions': True, 'external_accounts_registry': True,
            'canonical_exams': True, 'canonical_translations': True,
            'canonical_mail': True, 'canonical_tasks': False,
        },
    }
