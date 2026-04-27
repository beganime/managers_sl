# documents/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers

from analytics.models import Deal

from .models import (
    DocumentTemplate,
    GeneratedDocument,
    InfoSnippet,
    KnowledgeSection,
    KnowledgeSectionAttachment,
    KnowledgeTest,
    KnowledgeTestAttempt,
    TemplateField,
    TestQuestion,
)
from .review_guard import safe_get_document_review

User = get_user_model()


def build_absolute_file_url(request, field):
    if not field:
        return None

    try:
        url = field.url
    except Exception:
        return None

    if request:
        return request.build_absolute_uri(url)

    return url


def _copy_payload(data):
    return data.copy() if hasattr(data, 'copy') else dict(data or {})


def _first_file(request, names):
    files = getattr(request, 'FILES', {}) if request else {}
    for name in names:
        if name in files:
            return files[name]
    return None


def _normalize_attachment_type(value):
    value = str(value or '').strip().lower()
    if value in ('photo', 'picture', 'img'):
        return 'image'
    if value in ('url', 'external_url'):
        return 'link'
    return value or 'file'


class KnowledgeUserMiniSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'full_name', 'email')

    def get_full_name(self, obj):
        return f'{obj.first_name} {obj.last_name}'.strip() or obj.email


class KnowledgeSectionMiniSerializer(serializers.ModelSerializer):
    cover_image_url = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    full_path = serializers.CharField(read_only=True)

    class Meta:
        model = KnowledgeSection
        fields = (
            'id',
            'parent',
            'title',
            'slug',
            'description',
            'icon',
            'color',
            'cover_image_url',
            'file_url',
            'external_url',
            'full_path',
        )

    def get_cover_image_url(self, obj):
        return build_absolute_file_url(self.context.get('request'), obj.cover_image)

    def get_file_url(self, obj):
        return build_absolute_file_url(self.context.get('request'), obj.file)


class KnowledgeSectionAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_data = KnowledgeUserMiniSerializer(source='uploaded_by', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeSectionAttachment
        fields = (
            'id',
            'section',
            'uploaded_by',
            'uploaded_by_data',
            'title',
            'attachment_type',
            'file',
            'file_url',
            'url',
            'note',
            'order',
            'created_at',
        )
        read_only_fields = ('uploaded_by', 'created_at')
        extra_kwargs = {
            'file': {'required': False, 'allow_null': True},
            'url': {'required': False, 'allow_blank': True},
            'title': {'required': False, 'allow_blank': True},
            'note': {'required': False, 'allow_blank': True},
            'order': {'required': False},
            'attachment_type': {'required': False},
        }

    def to_internal_value(self, data):
        payload = _copy_payload(data)
        request = self.context.get('request')

        if 'type' in payload and 'attachment_type' not in payload:
            payload['attachment_type'] = payload.get('type')

        payload['attachment_type'] = _normalize_attachment_type(payload.get('attachment_type'))

        if 'file' not in payload:
            file_obj = _first_file(request, ('file', 'image', 'photo', 'attachment', 'upload', 'document'))
            if file_obj:
                payload['file'] = file_obj

        return super().to_internal_value(payload)

    def get_file_url(self, obj):
        return build_absolute_file_url(self.context.get('request'), obj.file)

    def validate(self, attrs):
        request = self.context.get('request')
        attachment_type = _normalize_attachment_type(attrs.get('attachment_type') or getattr(self.instance, 'attachment_type', 'file'))
        attrs['attachment_type'] = attachment_type

        file_value = attrs.get('file') or getattr(self.instance, 'file', None)
        url_value = attrs.get('url') or getattr(self.instance, 'url', '')

        if not file_value:
            file_value = _first_file(request, ('file', 'image', 'photo', 'attachment', 'upload', 'document'))
            if file_value:
                attrs['file'] = file_value

        if attachment_type in ('file', 'image') and not file_value:
            raise serializers.ValidationError({'file': 'Для файла/фото нужно загрузить файл.'})
        if attachment_type == 'link' and not str(url_value or '').strip():
            raise serializers.ValidationError({'url': 'Для ссылки нужно указать URL.'})
        return attrs


class KnowledgeSectionSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    attachments = KnowledgeSectionAttachmentSerializer(many=True, read_only=True)
    responsible_users_data = KnowledgeUserMiniSerializer(source='responsible_users', many=True, read_only=True)
    created_by_data = KnowledgeUserMiniSerializer(source='created_by', read_only=True)
    full_path = serializers.CharField(read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeSection
        fields = (
            'id',
            'parent',
            'title',
            'slug',
            'description',
            'icon',
            'color',
            'cover_image',
            'cover_image_url',
            'file',
            'file_url',
            'external_url',
            'responsible_users',
            'responsible_users_data',
            'created_by',
            'created_by_data',
            'order',
            'is_active',
            'created_at',
            'updated_at',
            'full_path',
            'children',
            'attachments',
        )
        read_only_fields = ('created_by', 'created_at', 'updated_at')
        extra_kwargs = {
            'cover_image': {'required': False, 'allow_null': True},
            'file': {'required': False, 'allow_null': True},
            'external_url': {'required': False, 'allow_blank': True},
            'description': {'required': False, 'allow_blank': True},
            'responsible_users': {'required': False},
            'order': {'required': False},
            'is_active': {'required': False},
            'icon': {'required': False, 'allow_blank': True},
            'color': {'required': False, 'allow_blank': True},
        }

    def to_internal_value(self, data):
        payload = _copy_payload(data)
        request = self.context.get('request')

        if 'cover_image' not in payload:
            cover = _first_file(request, ('cover_image', 'image', 'photo', 'cover', 'upload'))
            if cover:
                payload['cover_image'] = cover

        if 'file' not in payload:
            file_obj = _first_file(request, ('file', 'document', 'attachment'))
            if file_obj:
                payload['file'] = file_obj

        parent = payload.get('parent')
        if parent in ('', 'null', 'undefined'):
            payload['parent'] = None

        return super().to_internal_value(payload)

    def get_children(self, obj):
        children = obj.children.all().order_by('order', 'title')
        return KnowledgeSectionMiniSerializer(children, many=True, context=self.context).data

    def get_cover_image_url(self, obj):
        return build_absolute_file_url(self.context.get('request'), obj.cover_image)

    def get_file_url(self, obj):
        return build_absolute_file_url(self.context.get('request'), obj.file)


class InfoSnippetSerializer(serializers.ModelSerializer):
    section_title = serializers.CharField(source='section.title', read_only=True)
    section_data = KnowledgeSectionMiniSerializer(source='section', read_only=True)

    class Meta:
        model = InfoSnippet
        fields = (
            'id',
            'section',
            'section_title',
            'section_data',
            'category',
            'title',
            'content',
            'content_format',
            'order',
            'updated_at',
        )
        extra_kwargs = {
            'content_format': {'required': False},
            'section': {'required': False, 'allow_null': True},
            'order': {'required': False},
        }

    def to_internal_value(self, data):
        payload = _copy_payload(data)
        if payload.get('section') in ('', 'null', 'undefined'):
            payload['section'] = None
        return super().to_internal_value(payload)


class TestQuestionSerializer(serializers.ModelSerializer):
    correct = serializers.IntegerField(required=False, write_only=True)

    class Meta:
        model = TestQuestion
        fields = (
            'id',
            'text',
            'options',
            'correct',
            'order',
        )


class KnowledgeTestSerializer(serializers.ModelSerializer):
    questions = TestQuestionSerializer(many=True)
    section_title = serializers.CharField(source='section.title', read_only=True)
    section_data = KnowledgeSectionMiniSerializer(source='section', read_only=True)

    class Meta:
        model = KnowledgeTest
        fields = (
            'id',
            'section',
            'section_title',
            'section_data',
            'title',
            'description',
            'is_active',
            'created_at',
            'updated_at',
            'questions',
        )

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        test = KnowledgeTest.objects.create(**validated_data)

        for item in questions_data:
            TestQuestion.objects.create(test=test, **item)

        return test

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if questions_data is not None:
            instance.questions.all().delete()
            for item in questions_data:
                TestQuestion.objects.create(test=instance, **item)

        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)

        request = self.context.get('request')
        user = getattr(request, 'user', None)

        is_admin = bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or user.is_staff
                or getattr(user, 'role', None) == 'admin'
            )
        )

        if not is_admin:
            for question in data.get('questions', []):
                question.pop('correct', None)

        return data


class KnowledgeTestAttemptSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='test.title', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    percent = serializers.FloatField(read_only=True)

    class Meta:
        model = KnowledgeTestAttempt
        fields = (
            'id',
            'test',
            'test_title',
            'user',
            'user_email',
            'score',
            'total',
            'percent',
            'answers',
            'started_at',
            'completed_at',
        )


class TemplateFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateField
        fields = (
            'id',
            'key',
            'label',
            'field_type',
            'is_required',
            'order',
        )


class DocumentTemplateSerializer(serializers.ModelSerializer):
    fields = TemplateFieldSerializer(many=True, read_only=True)
    fields_config = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentTemplate
        fields = (
            'id',
            'title',
            'name',
            'description',
            'file_url',
            'is_active',
            'updated_at',
            'fields',
            'fields_config',
        )

    name = serializers.CharField(source='title', read_only=True)

    def get_file_url(self, obj):
        request = self.context.get('request')
        return build_absolute_file_url(request, obj.file)

    def get_fields_config(self, obj):
        return TemplateFieldSerializer(obj.fields.all().order_by('order'), many=True).data


class GeneratedDocumentSerializer(serializers.ModelSerializer):
    template = DocumentTemplateSerializer(read_only=True)
    template_id = serializers.PrimaryKeyRelatedField(
        source='template',
        queryset=DocumentTemplate.objects.filter(is_active=True),
        write_only=True,
        required=False,
    )

    deal = serializers.PrimaryKeyRelatedField(read_only=True)
    deal_id = serializers.PrimaryKeyRelatedField(
        source='deal',
        queryset=Deal.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )

    manager = serializers.PrimaryKeyRelatedField(read_only=True)
    manager_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    status_label = serializers.CharField(source='get_status_display', read_only=True)
    review_status = serializers.SerializerMethodField()
    rejection_reason = serializers.SerializerMethodField()

    file_url = serializers.SerializerMethodField()
    original_file_url = serializers.SerializerMethodField()
    approved_file_url = serializers.SerializerMethodField()

    can_download = serializers.BooleanField(read_only=True)
    can_download_original = serializers.BooleanField(read_only=True)
    can_download_approved = serializers.BooleanField(read_only=True)

    class Meta:
        model = GeneratedDocument
        fields = (
            'id',
            'template',
            'template_id',
            'deal',
            'deal_id',
            'manager',
            'manager_name',
            'title',
            'context_data',
            'status',
            'status_label',
            'review_status',
            'rejection_reason',
            'file_url',
            'original_file_url',
            'approved_file_url',
            'can_download',
            'can_download_original',
            'can_download_approved',
            'approved_by',
            'approved_by_name',
            'approved_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'status',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        )
        extra_kwargs = {
            'context_data': {'required': False},
            'title': {'required': False, 'allow_blank': True},
        }

    def to_internal_value(self, data):
        payload = _copy_payload(data)

        if 'template' in payload and 'template_id' not in payload:
            payload['template_id'] = payload.pop('template')

        if 'deal' in payload and 'deal_id' not in payload:
            payload['deal_id'] = payload.pop('deal')

        if payload.get('deal_id') in ('', 'null', 'undefined'):
            payload['deal_id'] = None

        if payload.get('context_data') in ('', None):
            payload['context_data'] = {}

        return super().to_internal_value(payload)

    def validate(self, attrs):
        if self.instance is None and 'template' not in attrs:
            raise serializers.ValidationError({'template_id': 'Поле template_id/template обязательно.'})
        return attrs

    def get_manager_name(self, obj):
        if not obj.manager:
            return None
        full = f'{obj.manager.first_name} {obj.manager.last_name}'.strip()
        return full or obj.manager.email

    def get_approved_by_name(self, obj):
        if not obj.approved_by:
            return None
        full = f'{obj.approved_by.first_name} {obj.approved_by.last_name}'.strip()
        return full or obj.approved_by.email

    def get_review_status(self, obj):
        review = safe_get_document_review(obj)
        if review:
            return review.status
        return 'pending'

    def get_rejection_reason(self, obj):
        review = safe_get_document_review(obj)
        if review:
            return review.rejection_reason or ''
        return ''

    def get_file_url(self, obj):
        request = self.context.get('request')
        return build_absolute_file_url(request, obj.generated_file)

    def get_original_file_url(self, obj):
        request = self.context.get('request')
        return build_absolute_file_url(request, obj.generated_file)

    def get_approved_file_url(self, obj):
        request = self.context.get('request')
        review = safe_get_document_review(obj)
        if not review or not review.approved_file:
            return None
        return build_absolute_file_url(request, review.approved_file)