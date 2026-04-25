# documents/serializers.py
from rest_framework import serializers

from analytics.models import Deal

from .models import (
    DocumentTemplate,
    GeneratedDocument,
    InfoSnippet,
    KnowledgeSection,
    KnowledgeTest,
    KnowledgeTestAttempt,
    TemplateField,
    TestQuestion,
)
from .review_guard import safe_get_document_review


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


class KnowledgeSectionSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    full_path = serializers.CharField(read_only=True)

    class Meta:
        model = KnowledgeSection
        fields = (
            'id',
            'parent',
            'title',
            'slug',
            'icon',
            'color',
            'order',
            'is_active',
            'created_at',
            'updated_at',
            'full_path',
            'children',
        )

    def get_children(self, obj):
        children = obj.children.all().order_by('order', 'title')
        return KnowledgeSectionSerializer(children, many=True, context=self.context).data


class InfoSnippetSerializer(serializers.ModelSerializer):
    section_title = serializers.CharField(source='section.title', read_only=True)

    class Meta:
        model = InfoSnippet
        fields = (
            'id',
            'section',
            'section_title',
            'category',
            'title',
            'content',
            'order',
            'updated_at',
        )


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

    class Meta:
        model = KnowledgeTest
        fields = (
            'id',
            'section',
            'section_title',
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
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentTemplate
        fields = (
            'id',
            'title',
            'description',
            'file_url',
            'is_active',
            'updated_at',
            'fields',
        )

    def get_file_url(self, obj):
        request = self.context.get('request')
        return build_absolute_file_url(request, obj.file)


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

    def validate(self, attrs):
        if self.instance is None and 'template' not in attrs:
            raise serializers.ValidationError({'template_id': 'Поле template_id обязательно.'})
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