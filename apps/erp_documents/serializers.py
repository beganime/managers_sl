from urllib.parse import quote

from rest_framework import serializers
from rest_framework.reverse import reverse

from apps.core.permissions import is_erp_admin
from .models import (
    DocumentApproval,
    DocumentDownloadLog,
    DocumentTemplate,
    DocumentTemplateField,
    GeneratedDocument,
    StampRule,
)


def build_file_url(request, file_field):
    if not file_field:
        return None
    try:
        url = file_field.url
    except ValueError:
        return None
    return request.build_absolute_uri(url) if request else url


def build_absolute_path(request, path):
    return request.build_absolute_uri(path) if request else path


def build_document_api_url(request, document, action):
    if not document or not document.pk:
        return None
    return build_absolute_path(request, f'/api/v1/documents/generated/{document.pk}/{action}/')


def build_document_portal_url(request, document, action):
    if not document or not document.pk:
        return None
    return build_absolute_path(request, f'/portal/documents/{document.pk}/{action}/')


class DocumentTemplateFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentTemplateField
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class DocumentTemplateSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    fields_config = DocumentTemplateFieldSerializer(source='fields', many=True, read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentTemplate
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_file_url(self, obj):
        return build_file_url(self.context.get('request'), obj.file)


class DocumentApprovalSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source='document.display_title', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approval_type_display = serializers.CharField(source='get_approval_type_display', read_only=True)

    class Meta:
        model = DocumentApproval
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'reviewed_by', 'reviewed_at')


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    application_title = serializers.SerializerMethodField()
    deal_title = serializers.CharField(source='deal.title', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
    stamp_preview_generated_by_name = serializers.CharField(source='stamp_preview_generated_by.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    display_title = serializers.CharField(read_only=True)
    approval = DocumentApprovalSerializer(read_only=True)

    generated_file_url = serializers.SerializerMethodField()
    stamp_preview_file_url = serializers.SerializerMethodField()
    approved_file_url = serializers.SerializerMethodField()

    generated_file_name = serializers.SerializerMethodField()
    approved_file_name = serializers.SerializerMethodField()
    stamp_preview_file_name = serializers.SerializerMethodField()

    download_original_url = serializers.SerializerMethodField()
    download_approved_url = serializers.SerializerMethodField()
    preview_approved_url = serializers.SerializerMethodField()
    stamp_preview_url = serializers.SerializerMethodField()

    portal_download_original_url = serializers.SerializerMethodField()
    portal_download_approved_url = serializers.SerializerMethodField()
    portal_preview_approved_url = serializers.SerializerMethodField()
    portal_stamp_preview_url = serializers.SerializerMethodField()
    portal_review_url = serializers.SerializerMethodField()
    portal_regenerate_url = serializers.SerializerMethodField()

    links = serializers.SerializerMethodField()

    preview_url = serializers.SerializerMethodField()
    download_docx_url = serializers.SerializerMethodField()
    download_pdf_url = serializers.SerializerMethodField()
    approved_pdf_url = serializers.SerializerMethodField()
    original_docx_url = serializers.SerializerMethodField()
    can_download_docx = serializers.SerializerMethodField()
    can_download_pdf = serializers.SerializerMethodField()
    can_preview = serializers.SerializerMethodField()
    can_approve = serializers.SerializerMethodField()
    can_reject = serializers.SerializerMethodField()
    can_download_original = serializers.BooleanField(read_only=True)
    can_download_approved = serializers.BooleanField(read_only=True)
    can_download = serializers.BooleanField(read_only=True)
    has_stamp_preview = serializers.BooleanField(read_only=True)

    class Meta:
        model = GeneratedDocument
        fields = '__all__'
        read_only_fields = (
            'status',
            'generated_file',
            'stamp_preview_file',
            'stamp_preview_options',
            'stamp_preview_generated_at',
            'stamp_preview_generated_by',
            'approved_file',
            'generation_error',
            'submitted_at',
            'generated_at',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )

    def get_generated_file_url(self, obj):
        return build_file_url(self.context.get('request'), obj.generated_file)

    def get_stamp_preview_file_url(self, obj):
        return build_file_url(self.context.get('request'), obj.stamp_preview_file)

    def get_approved_file_url(self, obj):
        return build_file_url(self.context.get('request'), obj.approved_file)

    def get_generated_file_name(self, obj):
        return obj.download_filename(DocumentDownloadLog.FILE_TYPE_ORIGINAL) if obj.generated_file else ''

    def get_approved_file_name(self, obj):
        return obj.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED) if obj.approved_file else ''

    def get_stamp_preview_file_name(self, obj):
        return obj.download_filename(DocumentDownloadLog.FILE_TYPE_APPROVED) if obj.stamp_preview_file else ''

    def get_download_original_url(self, obj):
        if not obj.can_download_original:
            return None
        return build_document_api_url(self.context.get('request'), obj, 'download-original')

    def get_download_approved_url(self, obj):
        if not obj.can_download_approved:
            return None
        return build_document_api_url(self.context.get('request'), obj, 'download-approved')

    def get_preview_approved_url(self, obj):
        if not obj.can_download_approved:
            return None
        return build_document_api_url(self.context.get('request'), obj, 'preview-approved')

    def get_stamp_preview_url(self, obj):
        if not obj.has_stamp_preview:
            return None
        return build_document_api_url(self.context.get('request'), obj, 'preview-stamp-preview')

    def get_portal_download_original_url(self, obj):
        if not obj.can_download_original:
            return None
        return build_document_portal_url(self.context.get('request'), obj, 'download-original')

    def get_portal_download_approved_url(self, obj):
        if not obj.can_download_approved:
            return None
        return build_document_portal_url(self.context.get('request'), obj, 'download-approved')

    def get_portal_preview_approved_url(self, obj):
        if not obj.can_download_approved:
            return None
        return build_document_portal_url(self.context.get('request'), obj, 'preview-approved')

    def get_portal_stamp_preview_url(self, obj):
        if not obj.has_stamp_preview:
            return None
        return build_document_portal_url(self.context.get('request'), obj, 'preview-stamp-preview')

    def get_portal_review_url(self, obj):
        if not obj.pk:
            return None
        return build_absolute_path(self.context.get('request'), f'/portal/documents/{obj.pk}/review/')

    def get_portal_regenerate_url(self, obj):
        if not obj.pk or obj.status == GeneratedDocument.STATUS_APPROVED:
            return None
        return build_absolute_path(self.context.get('request'), f'/portal/documents/{obj.pk}/regenerate/')

    def get_links(self, obj):
        return {
            'api': {
                'download_original': self.get_download_original_url(obj),
                'download_approved': self.get_download_approved_url(obj),
                'preview_approved': self.get_preview_approved_url(obj),
                'stamp_preview': self.get_stamp_preview_url(obj),
            },
            'portal': {
                'download_original': self.get_portal_download_original_url(obj),
                'download_approved': self.get_portal_download_approved_url(obj),
                'preview_approved': self.get_portal_preview_approved_url(obj),
                'stamp_preview': self.get_portal_stamp_preview_url(obj),
                'review': self.get_portal_review_url(obj),
                'regenerate': self.get_portal_regenerate_url(obj),
            },
            'files': {
                'generated_file': self.get_generated_file_url(obj),
                'approved_file': self.get_approved_file_url(obj),
                'stamp_preview_file': self.get_stamp_preview_file_url(obj),
            },
        }

    def build_action_url(self, obj, action_name):
        request = self.context.get('request')
        if not request:
            return None
        return reverse(
            f'erp-generated-document-{action_name}',
            kwargs={'pk': obj.pk},
            request=request,
        )

    def get_preview_url(self, obj):
        if not self.get_can_preview(obj):
            return None
        return self.build_action_url(obj, 'preview')

    def get_download_docx_url(self, obj):
        if not self.get_can_download_docx(obj):
            return None
        return self.build_action_url(obj, 'download-docx')

    def get_download_pdf_url(self, obj):
        if not self.get_can_download_pdf(obj):
            return None
        return self.build_action_url(obj, 'download-pdf')

    def get_approved_pdf_url(self, obj):
        return self.get_download_pdf_url(obj)

    def get_original_docx_url(self, obj):
        return build_file_url(self.context.get('request'), obj.generated_file)

    def get_can_download_docx(self, obj):
        return bool(obj.generated_file and obj.status in {
            GeneratedDocument.STATUS_GENERATED,
            GeneratedDocument.STATUS_PENDING,
            GeneratedDocument.STATUS_APPROVED,
            GeneratedDocument.STATUS_REJECTED,
        })

    def get_can_download_pdf(self, obj):
        return bool(obj.can_download_approved)

    def get_can_preview(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if obj.stamp_preview_file:
            return bool(user and user.is_authenticated and is_erp_admin(user))
        return self.get_can_download_docx(obj)

    def get_can_approve(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(
            user
            and user.is_authenticated
            and is_erp_admin(user)
            and obj.generated_file
            and obj.status not in {GeneratedDocument.STATUS_APPROVED, GeneratedDocument.STATUS_REJECTED}
        )

    def get_can_reject(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(
            user
            and user.is_authenticated
            and is_erp_admin(user)
            and obj.status not in {GeneratedDocument.STATUS_APPROVED, GeneratedDocument.STATUS_REJECTED}
        )

    def get_application_title(self, obj):
        return str(obj.application) if obj.application_id else ''


class StampRuleSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)
    stamp_image_url = serializers.SerializerMethodField()

    class Meta:
        model = StampRule
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_stamp_image_url(self, obj):
        return build_file_url(self.context.get('request'), obj.stamp_image)


class DocumentDownloadLogSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(source='document.display_title', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)

    class Meta:
        model = DocumentDownloadLog
        fields = '__all__'
        read_only_fields = ('created_at',)
