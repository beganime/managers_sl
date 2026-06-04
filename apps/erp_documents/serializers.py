from rest_framework import serializers

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
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


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
    document_title = serializers.CharField(source='document.title', read_only=True)
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
    approval = DocumentApprovalSerializer(read_only=True)
    generated_file_url = serializers.SerializerMethodField()
    stamp_preview_file_url = serializers.SerializerMethodField()
    approved_file_url = serializers.SerializerMethodField()
    can_download_original = serializers.BooleanField(read_only=True)
    can_download_approved = serializers.BooleanField(read_only=True)
    can_download = serializers.BooleanField(read_only=True)

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
    document_title = serializers.CharField(source='document.title', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    file_type_display = serializers.CharField(source='get_file_type_display', read_only=True)

    class Meta:
        model = DocumentDownloadLog
        fields = '__all__'
        read_only_fields = ('created_at',)
