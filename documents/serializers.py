# documents/serializers.py
from rest_framework import serializers

from .models import (
    InfoSnippet,
    DocumentTemplate,
    TemplateField,
    GeneratedDocument,
    KnowledgeTest,
    TestQuestion,
)


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or getattr(user, 'role', None) == 'admin'
        )
    )


class InfoSnippetSerializer(serializers.ModelSerializer):
    class Meta:
        model = InfoSnippet
        fields = '__all__'


class TemplateFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateField
        fields = ('key', 'label', 'field_type', 'is_required', 'order')


class DocumentTemplateSerializer(serializers.ModelSerializer):
    fields_config = TemplateFieldSerializer(source='fields', many=True, read_only=True)

    class Meta:
        model = DocumentTemplate
        fields = (
            'id',
            'title',
            'description',
            'file',
            'is_active',
            'updated_at',
            'fields_config',
        )


class TestQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestQuestion
        fields = ('id', 'text', 'options', 'correct', 'order')


class KnowledgeTestSerializer(serializers.ModelSerializer):
    questions = TestQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = KnowledgeTest
        fields = (
            'id',
            'title',
            'description',
            'questions',
            'updated_at',
        )


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.title', read_only=True)
    deal_client_name = serializers.CharField(source='deal.client.full_name', read_only=True)
    can_download = serializers.BooleanField(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedDocument
        fields = (
            'id',
            'template',
            'template_name',
            'manager',
            'deal',
            'deal_client_name',
            'title',
            'context_data',
            'status',
            'generated_file',
            'file_url',
            'can_download',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'manager',
            'status',
            'generated_file',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )

    def get_file_url(self, obj):
        if not obj.can_download or not obj.generated_file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.generated_file.url)
        return obj.generated_file.url

    def validate_context_data(self, value):
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('context_data должен быть JSON-объектом.')
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        instance = getattr(self, 'instance', None)

        template = attrs.get('template') if 'template' in attrs else (instance.template if instance else None)
        deal = attrs.get('deal') if 'deal' in attrs else (instance.deal if instance else None)

        if instance and instance.status == 'approved':
            raise serializers.ValidationError('Одобренный документ нельзя редактировать.')

        if template and not template.is_active:
            raise serializers.ValidationError({'template': 'Нельзя использовать неактивный шаблон.'})

        if deal and not is_admin_user(user) and deal.manager_id != user.id:
            raise serializers.ValidationError({
                'deal': 'Менеджер не может создавать документ по чужой сделке.'
            })

        return attrs