"""
Runtime fixes for ERP document generation.

The important rule here is simple:
the final approved PDF with stamp must be the same file that the
administrator checked in the stamp preview.
"""

from pathlib import Path
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound

from .models import (
    DocumentApproval,
    DocumentDownloadLog,
    GeneratedDocument,
    safe_file_slug,
)


def _normalize_stamp_options(options):
    normalized = {}
    for key, value in (options or {}).items():
        if value in (None, ''):
            continue
        if isinstance(value, bool):
            normalized[str(key)] = value
        else:
            normalized[str(key)] = str(value).strip()
    return normalized


def _copy_stamp_preview_file(document):
    if not document.stamp_preview_file:
        raise ValueError('Сначала сгенерируйте предпросмотр PDF с печатью и проверьте его.')

    document.stamp_preview_file.open('rb')
    try:
        content = document.stamp_preview_file.read()
    finally:
        document.stamp_preview_file.close()

    if not content:
        raise ValueError('Файл предпросмотра PDF с печатью пустой. Сгенерируйте предпросмотр заново.')

    extension = Path(document.stamp_preview_file.name or '').suffix.lower() or '.pdf'
    if extension != '.pdf':
        extension = '.pdf'

    base = safe_file_slug(document.display_title, 'approved-document')
    return f'{base}-stamped-{uuid4().hex[:10]}{extension}', ContentFile(content)


def _patched_approve_stamp_preview(self, user, comment=''):
    approved = self.already_approved_result(
        user,
        DocumentApproval.TYPE_WITH_STAMP,
        comment=comment,
    )
    if approved:
        return approved

    if not self.stamp_preview_file:
        raise ValueError('Сначала сгенерируйте предпросмотр PDF с печатью и проверьте его.')
    if not self.template.allow_with_stamp:
        raise ValueError('Этот шаблон не разрешает PDF с электронной печатью.')

    stamp_options = self.stamp_preview_options or {'stamp_mode': 'executor'}
    approved_file = _copy_stamp_preview_file(self)

    with transaction.atomic():
        if self.approved_file:
            self.approved_file.delete(save=False)

        self.approved_file.save(approved_file[0], approved_file[1], save=False)
        self.status = self.STATUS_APPROVED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.generation_error = ''

        stored_context = dict(self.context_data or {})
        stored_context['last_stamp_options'] = stamp_options
        stored_context['approved_from_stamp_preview'] = True
        stored_context['approved_from_original_docx'] = False
        self.context_data = stored_context

        self.save(update_fields=[
            'approved_file',
            'status',
            'approved_by',
            'approved_at',
            'generation_error',
            'context_data',
            'updated_at',
        ])

        self.mark_approval_record_approved(
            user,
            DocumentApproval.TYPE_WITH_STAMP,
            comment=comment,
            reviewed_at=self.approved_at,
        )

    return self


def _patch_generated_document_model():
    if getattr(GeneratedDocument, '_preview_approval_patch_applied', False):
        return

    original_approve = GeneratedDocument.approve

    def approve(self, user, with_stamp=False, comment='', stamp_options=None):
        if with_stamp and self.stamp_preview_file:
            requested_options = _normalize_stamp_options(stamp_options)
            preview_options = _normalize_stamp_options(self.stamp_preview_options)

            if not requested_options or requested_options == preview_options:
                return self.approve_stamp_preview(user=user, comment=comment)

        return original_approve(
            self,
            user=user,
            with_stamp=with_stamp,
            comment=comment,
            stamp_options=stamp_options,
        )

    GeneratedDocument._original_approve_before_preview_patch = original_approve
    GeneratedDocument.approve_stamp_preview = _patched_approve_stamp_preview
    GeneratedDocument.approve = approve
    GeneratedDocument._preview_approval_patch_applied = True


def _patch_generated_document_viewset():
    from .views import GeneratedDocumentViewSet

    if getattr(GeneratedDocumentViewSet, '_approved_preview_action_patch_applied', False):
        return

    def preview_approved(self, request, pk=None):
        document = self.get_object()
        if not document.can_download_approved:
            raise NotFound('Approved document is not available for preview.')

        response = FileResponse(
            document.approved_file.open('rb'),
            as_attachment=False,
            filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED),
        )
        if document.approved_file_is_pdf:
            response['Content-Type'] = 'application/pdf'
        return response

    preview_approved.__name__ = 'preview_approved'
    preview_approved.__doc__ = 'Inline preview for approved final PDF.'
    GeneratedDocumentViewSet.preview_approved = action(
        detail=True,
        methods=['get'],
        url_path='preview-approved',
    )(preview_approved)

    def preview_pdf(self, request, pk=None):
        return self.preview_approved(request, pk=pk)

    preview_pdf.__name__ = 'preview_pdf'
    preview_pdf.__doc__ = 'Backward-compatible inline preview for approved PDF.'
    GeneratedDocumentViewSet.preview_pdf = action(
        detail=True,
        methods=['get'],
        url_path='preview-pdf',
    )(preview_pdf)

    GeneratedDocumentViewSet._approved_preview_action_patch_applied = True


def apply_document_generation_patches():
    _patch_generated_document_model()
    _patch_generated_document_viewset()
