from rest_framework import serializers

from .models import (
    InfoSnippet,
    DocumentTemplate,
    TemplateField,
    GeneratedDocument,
    KnowledgeTest,
    TestQuestion,
    KnowledgeTestAttempt,
)


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or getattr(user, 'role', None) == 'admin' or user.is_staff
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
    questions = TestQuestionSerializer(many=True)

    class Meta:
        model = KnowledgeTest
        fields = (
            'id',
            'title',
            'description',
            'questions',
            'updated_at',
        )

    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        test = KnowledgeTest.objects.create(**validated_data)

        for index, question in enumerate(questions_data):
            TestQuestion.objects.create(
                test=test,
                text=question.get('text', ''),
                options=question.get('options', []),
                correct=question.get('correct', 0),
                order=question.get('order', index),
            )

        return test

    def update(self, instance, validated_data):
        questions_data = validated_data.pop('questions', None)

        instance.title = validated_data.get('title', instance.title)
        instance.description = validated_data.get('description', instance.description)
        instance.save()

        if questions_data is not None:
            instance.questions.all().delete()
            for index, question in enumerate(questions_data):
                TestQuestion.objects.create(
                    test=instance,
                    text=question.get('text', ''),
                    options=question.get('options', []),
                    correct=question.get('correct', 0),
                    order=question.get('order', index),
                )

        return instance


class KnowledgeTestAttemptSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    test_title = serializers.CharField(source='test.title', read_only=True)
    percent = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeTestAttempt
        fields = (
            'id',
            'test',
            'test_title',
            'user',
            'user_name',
            'score',
            'total',
            'percent',
            'answers',
            'started_at',
            'completed_at',
        )
        read_only_fields = fields

    def get_user_name(self, obj):
        full = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full or obj.user.email or f"ID {obj.user_id}"

    def get_percent(self, obj):
        return obj.percent


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