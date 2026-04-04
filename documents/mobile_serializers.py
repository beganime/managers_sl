from rest_framework import serializers

from .models import GeneratedDocument
from .review_models import DocumentReview, resolve_document_status


class GeneratedDocumentMobileSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    manager_name = serializers.SerializerMethodField()
    deal_client_name = serializers.SerializerMethodField()
    can_download = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    approved_file_url = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    rejection_reason = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedDocument
        fields = (
            'id',
            'template',
            'template_name',
            'manager',
            'manager_name',
            'deal',
            'deal_client_name',
            'title',
            'context_data',
            'status',
            'generated_file',
            'file_url',
            'approved_file_url',
            'can_download',
            'rejection_reason',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'status',
            'generated_file',
            'file_url',
            'approved_file_url',
            'can_download',
            'rejection_reason',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )

    def get_manager_name(self, obj):
        manager = getattr(obj, 'manager', None)
        if not manager:
            return None
        return f'{manager.first_name} {manager.last_name}'.strip() or manager.email

    def get_deal_client_name(self, obj):
        deal = getattr(obj, 'deal', None)
        client = getattr(deal, 'client', None) if deal else None
        if not client:
            return None
        return f'{client.first_name} {client.last_name}'.strip() or getattr(client, 'email', None)

    def get_status(self, obj):
        return resolve_document_status(obj)

    def get_rejection_reason(self, obj):
        review = getattr(obj, 'review', None)
        return getattr(review, 'rejection_reason', '') if review else ''

    def get_can_download(self, obj):
        review = getattr(obj, 'review', None)
        if review and review.status == 'approved' and review.approved_file:
            return True
        return False

    def _build_url(self, file_field):
        if not file_field:
            return None
        try:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(file_field.url)
            return file_field.url
        except Exception:
            return None

    def get_file_url(self, obj):
        return self._build_url(getattr(obj, 'generated_file', None))

    def get_approved_file_url(self, obj):
        review = getattr(obj, 'review', None)
        if review and review.approved_file:
            return self._build_url(review.approved_file)
        return None