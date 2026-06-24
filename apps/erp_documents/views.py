from django.db.models import Q
from django.http import FileResponse
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.permissions import filter_by_company_scope, filter_by_office_scope, get_employee_profile, is_erp_admin
from apps.crm.models import Application, Client
from apps.finance.models import Deal

from .models import (
    DocumentApproval,
    DocumentDownloadLog,
    DocumentTemplate,
    DocumentTemplateField,
    GeneratedDocument,
    StampRule,
)
from .serializers import (
    DocumentApprovalSerializer,
    DocumentDownloadLogSerializer,
    DocumentTemplateFieldSerializer,
    DocumentTemplateSerializer,
    GeneratedDocumentSerializer,
    StampRuleSerializer,
)


TRUE_VALUES = {'1', 'true', 'True', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'False', 'no', 'off'}


def parse_bool(value):
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


def stamp_options_from_request(data):
    stamp_position = data.get('stamp_position') or data.get('position') or ''
    has_manual_coordinates = data.get('stamp_x_mm') or data.get('x_mm') or data.get('stamp_y_mm') or data.get('y_mm')
    stamp_mode = data.get('stamp_mode') or ''
    if not stamp_mode:
        stamp_mode = 'manual' if stamp_position == 'custom' or has_manual_coordinates else 'position' if stamp_position else 'executor'

    return {
        'stamp_mode': stamp_mode,
        'stamp_position': stamp_position,
        'position': stamp_position,
        'stamp_width_mm': data.get('stamp_width_mm') or data.get('width_mm') or '',
        'stamp_height_mm': data.get('stamp_height_mm') or data.get('height_mm') or '',
        'stamp_x_percent': data.get('stamp_x_percent') or '',
        'stamp_y_percent': data.get('stamp_y_percent') or '',
        'stamp_x_mm': data.get('stamp_x_mm') or data.get('x_mm') or '',
        'stamp_y_mm': data.get('stamp_y_mm') or data.get('y_mm') or '',
        'page_number': data.get('page_number') or '',
        'watermark_enabled': data.get('watermark_enabled'),
        'watermark_text': data.get('watermark_text') or '',
    }


def request_includes_stamp_options(data):
    return any(
        key in data
        for key in (
            'stamp_position',
            'position',
            'stamp_width_mm',
            'stamp_height_mm',
            'stamp_x_mm',
            'stamp_y_mm',
            'width_mm',
            'height_mm',
            'x_mm',
            'y_mm',
            'watermark_enabled',
            'watermark_text',
        )
    )


def default_company_office(user):
    employee = get_employee_profile(user)
    if not employee:
        return {}
    data = {'company': employee.company}
    if employee.office_id:
        data['office'] = employee.office
    return data


def template_scope(qs, user):
    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True)

    return qs.filter(Q(company=employee.company) | Q(company__isnull=True))


def ensure_admin(user):
    if not is_erp_admin(user):
        raise PermissionDenied('Only administrators can perform this action.')


def request_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_download(request, document, file_type):
    DocumentDownloadLog.objects.create(
        document=document,
        user=request.user if request.user.is_authenticated else None,
        file_type=file_type,
        ip_address=request_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )


def apply_common_filters(qs, request, *, search_fields=(), date_field='created_at'):
    company = request.query_params.get('company')
    if company:
        qs = qs.filter(company_id=company)

    office = request.query_params.get('office')
    if office and hasattr(qs.model, 'office'):
        qs = qs.filter(office_id=office)

    status_value = request.query_params.get('status')
    if status_value and hasattr(qs.model, 'status'):
        qs = qs.filter(status=status_value)

    template = request.query_params.get('template')
    if template and hasattr(qs.model, 'template'):
        qs = qs.filter(template_id=template)

    client = request.query_params.get('client')
    if client and hasattr(qs.model, 'client'):
        qs = qs.filter(client_id=client)

    manager = request.query_params.get('manager')
    if manager and hasattr(qs.model, 'manager'):
        qs = qs.filter(manager_id=manager)

    date_from = request.query_params.get('date_from')
    if date_from and date_field:
        qs = qs.filter(**{f'{date_field}__gte': date_from})

    date_to = request.query_params.get('date_to')
    if date_to and date_field:
        qs = qs.filter(**{f'{date_field}__lte': date_to})

    search = request.query_params.get('search')
    if search and search_fields:
        query = Q()
        for field in search_fields:
            query |= Q(**{f'{field}__icontains': search})
        qs = qs.filter(query)

    return qs


class DocumentTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = DocumentTemplate.objects.select_related('company', 'created_by').prefetch_related('fields')
        qs = template_scope(qs, self.request.user)

        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        qs = apply_common_filters(qs, self.request, search_fields=('name', 'code', 'description', 'company__name'))
        return qs.order_by('company__name', 'name')

    def perform_create(self, serializer):
        data = {}
        if not is_erp_admin(self.request.user):
            defaults = default_company_office(self.request.user)
            if defaults.get('company'):
                data['company'] = defaults['company']
        serializer.save(created_by=self.request.user, **data)

    @action(detail=True, methods=['post'], url_path='generate')
    def generate(self, request, pk=None):
        template = self.get_object()
        document = create_generated_document(template, request)
        document.generate_file()
        if template.requires_approval:
            document.submit_for_approval(user=request.user, comment=request.data.get('comment', ''))
        serializer = GeneratedDocumentSerializer(document, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentTemplateFieldViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentTemplateFieldSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DocumentTemplateField.objects.select_related('template', 'template__company')
        if not is_erp_admin(self.request.user):
            employee = get_employee_profile(self.request.user)
            if not employee:
                qs = qs.filter(template__company__isnull=True)
            else:
                qs = qs.filter(Q(template__company=employee.company) | Q(template__company__isnull=True))
        template = self.request.query_params.get('template')
        if template:
            qs = qs.filter(template_id=template)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(key__icontains=search) | Q(label__icontains=search))
        return qs.order_by('template__name', 'sort_order', 'label')


class GeneratedDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = GeneratedDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = GeneratedDocument.objects.select_related(
            'company',
            'office',
            'template',
            'client',
            'application',
            'deal',
            'manager',
            'approved_by',
            'approval',
        )
        qs = filter_by_office_scope(qs, self.request.user)

        if not is_erp_admin(self.request.user):
            qs = qs.filter(Q(manager=self.request.user) | Q(client__shared_with=self.request.user)).distinct()

        qs = apply_common_filters(
            qs,
            self.request,
            search_fields=('title', 'template__name', 'client__full_name', 'client__phone', 'deal__title'),
        )
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        data = {}
        if not is_erp_admin(self.request.user):
            data.update(default_company_office(self.request.user))
        if not serializer.validated_data.get('manager'):
            data['manager'] = self.request.user
        serializer.save(**data)

    @action(detail=True, methods=['post'], url_path='generate')
    def generate(self, request, pk=None):
        document = self.get_object()
        if document.status == GeneratedDocument.STATUS_APPROVED:
            raise ValidationError('Approved document cannot be regenerated.')
        document.context_data.update(request.data.get('context_data') or {})
        document.save(update_fields=['context_data', 'updated_at'])
        document.generate_file()
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='submit-for-approval')
    def submit_for_approval(self, request, pk=None):
        document = self.get_object()
        document.submit_for_approval(user=request.user, comment=request.data.get('comment', ''))
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        ensure_admin(request.user)
        document = self.get_object()
        mode = request.data.get('approval_type') or request.data.get('mode') or ''
        with_stamp = parse_bool(request.data.get('with_stamp'))
        if with_stamp is None:
            with_stamp = mode in ('with_stamp', 'approve_with_stamp') or request_includes_stamp_options(request.data)
        try:
            document.approve(
                user=request.user,
                with_stamp=with_stamp,
                comment=request.data.get('comment', ''),
                stamp_options=stamp_options_from_request(request.data) if with_stamp else None,
            )
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='generate-stamp-preview')
    def generate_stamp_preview(self, request, pk=None):
        ensure_admin(request.user)
        document = self.get_object()
        try:
            document.generate_stamp_preview(
                user=request.user,
                stamp_options=stamp_options_from_request(request.data),
            )
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='approve-stamp-preview')
    def approve_stamp_preview(self, request, pk=None):
        ensure_admin(request.user)
        document = self.get_object()
        try:
            document.approve_stamp_preview(
                user=request.user,
                comment=request.data.get('comment', ''),
            )
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        ensure_admin(request.user)
        document = self.get_object()
        document.reject(user=request.user, reason=request.data.get('reason') or request.data.get('rejection_reason') or '')
        return Response(self.get_serializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='download-original')
    def download_original(self, request, pk=None):
        document = self.get_object()
        if not document.can_download_original:
            raise NotFound('Original DOCX document is not available for download.')
        log_download(request, document, DocumentDownloadLog.FILE_TYPE_ORIGINAL)
        return FileResponse(document.generated_file.open('rb'), as_attachment=True, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_ORIGINAL))

    @action(detail=True, methods=['get'], url_path='download-docx')
    def download_docx(self, request, pk=None):
        document = self.get_object()
        if not document.generated_file or document.status not in {
            GeneratedDocument.STATUS_GENERATED,
            GeneratedDocument.STATUS_PENDING,
            GeneratedDocument.STATUS_APPROVED,
            GeneratedDocument.STATUS_REJECTED,
        }:
            raise NotFound('DOCX document is not available for download.')
        log_download(request, document, DocumentDownloadLog.FILE_TYPE_ORIGINAL)
        return FileResponse(document.generated_file.open('rb'), as_attachment=True, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_ORIGINAL))

    @action(detail=True, methods=['get'], url_path='download-approved')
    def download_approved(self, request, pk=None):
        document = self.get_object()
        if not document.can_download_approved:
            raise NotFound('Approved document is not available for download.')
        log_download(request, document, DocumentDownloadLog.FILE_TYPE_APPROVED)
        return FileResponse(document.approved_file.open('rb'), as_attachment=True, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED))

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        return self.download_approved(request, pk=pk)

    @action(detail=True, methods=['get'], url_path='preview')
    def preview(self, request, pk=None):
        document = self.get_object()
        if document.stamp_preview_file:
            ensure_admin(request.user)
            response = FileResponse(
                document.stamp_preview_file.open('rb'),
                as_attachment=False,
                filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED),
            )
            response['Content-Type'] = 'application/pdf'
            return response
        if document.generated_file and document.status in {
            GeneratedDocument.STATUS_GENERATED,
            GeneratedDocument.STATUS_PENDING,
            GeneratedDocument.STATUS_APPROVED,
            GeneratedDocument.STATUS_REJECTED,
        }:
            return FileResponse(
                document.generated_file.open('rb'),
                as_attachment=False,
                filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_ORIGINAL),
            )
        raise NotFound('Document preview is not available.')

    @action(detail=True, methods=['get'], url_path='preview-stamp-preview')
    def preview_stamp_preview(self, request, pk=None):
        ensure_admin(request.user)
        document = self.get_object()
        if not document.stamp_preview_file:
            raise NotFound('Stamp preview is not available yet.')
        response = FileResponse(document.stamp_preview_file.open('rb'), as_attachment=False, filename=document.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED))
        response['Content-Type'] = 'application/pdf'
        return response


class DocumentApprovalViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentApprovalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DocumentApproval.objects.select_related('document', 'document__company', 'document__office', 'document__client', 'reviewed_by')
        qs = filter_by_office_scope(qs, self.request.user, company_field='document__company', office_field='document__office')
        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(document__title__icontains=search) | Q(document__client__full_name__icontains=search))
        return qs.order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        ensure_admin(request.user)
        approval = self.get_object()
        mode = request.data.get('approval_type') or request.data.get('mode') or ''
        with_stamp = parse_bool(request.data.get('with_stamp'))
        if with_stamp is None:
            with_stamp = mode in ('with_stamp', 'approve_with_stamp') or request_includes_stamp_options(request.data)
        try:
            approval.document.approve(
                user=request.user,
                with_stamp=with_stamp,
                comment=request.data.get('comment', ''),
                stamp_options=stamp_options_from_request(request.data) if with_stamp else None,
            )
        except ValueError as exc:
            raise ValidationError(str(exc))
        approval.refresh_from_db()
        return Response(self.get_serializer(approval).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        ensure_admin(request.user)
        approval = self.get_object()
        approval.document.reject(user=request.user, reason=request.data.get('reason') or request.data.get('rejection_reason') or '')
        approval.refresh_from_db()
        return Response(self.get_serializer(approval).data, status=status.HTTP_200_OK)


class StampRuleViewSet(viewsets.ModelViewSet):
    serializer_class = StampRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = StampRule.objects.select_related('company', 'office', 'template')
        qs = template_scope(qs, self.request.user)

        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        qs = apply_common_filters(qs, self.request, search_fields=('name', 'company__name', 'office__name', 'template__name'))
        return qs.order_by('sort_order', 'name')

    def perform_create(self, serializer):
        if is_erp_admin(self.request.user) or serializer.validated_data.get('company'):
            serializer.save()
            return
        defaults = default_company_office(self.request.user)
        serializer.save(company=defaults.get('company'), office=defaults.get('office'))


class DocumentDownloadLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DocumentDownloadLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DocumentDownloadLog.objects.select_related('document', 'document__company', 'document__office', 'document__client', 'user')
        qs = filter_by_office_scope(qs, self.request.user, company_field='document__company', office_field='document__office')
        document = self.request.query_params.get('document')
        if document:
            qs = qs.filter(document_id=document)
        file_type = self.request.query_params.get('file_type')
        if file_type:
            qs = qs.filter(file_type=file_type)
        return qs.order_by('-created_at')


def create_generated_document(template, request):
    data = request.data
    client = Client.objects.filter(pk=data.get('client')).first() if data.get('client') else None
    application = Application.objects.filter(pk=data.get('application')).select_related('client', 'company', 'office', 'manager').first() if data.get('application') else None
    deal = Deal.objects.filter(pk=data.get('deal')).select_related('client', 'application', 'company', 'office', 'manager').first() if data.get('deal') else None

    if deal:
        client = client or deal.client
        application = application or deal.application
        company = deal.company
        office = deal.office
        manager = deal.manager
    elif application:
        client = client or application.client
        company = application.company
        office = application.office
        manager = application.manager
    elif client:
        company = client.company
        office = client.office
        manager = client.manager
    else:
        defaults = default_company_office(request.user)
        company = template.company or defaults.get('company')
        office = defaults.get('office')
        manager = request.user

    if not company:
        raise ValidationError('Company is required to generate a document.')

    title = data.get('title') or template.name
    context_data = data.get('context_data') or {}

    return GeneratedDocument.objects.create(
        company=company,
        office=office,
        template=template,
        client=client,
        application=application,
        deal=deal,
        manager=manager or request.user,
        title=title,
        context_data=context_data,
    )
