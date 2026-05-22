from rest_framework import serializers

from apps.core.permissions import is_erp_admin

from .models import (
    ArticleReadLog,
    KnowledgeArticle,
    KnowledgeAttachment,
    KnowledgeCategory,
    KnowledgeQuestion,
    KnowledgeTest,
    KnowledgeTestAttempt,
)


def build_file_url(request, file_field):
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


class KnowledgeCategorySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    articles_count = serializers.IntegerField(source='articles.count', read_only=True)

    class Meta:
        model = KnowledgeCategory
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')


class KnowledgeAttachmentSerializer(serializers.ModelSerializer):
    article_title = serializers.CharField(source='article.title', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeAttachment
        fields = '__all__'
        read_only_fields = ('uploaded_by', 'created_at', 'updated_at')

    def get_file_url(self, obj):
        return build_file_url(self.context.get('request'), obj.file)

    def validate(self, attrs):
        attachment_type = attrs.get('attachment_type') or getattr(self.instance, 'attachment_type', KnowledgeAttachment.TYPE_FILE)
        file_value = attrs.get('file') or getattr(self.instance, 'file', None)
        url_value = attrs.get('url') or getattr(self.instance, 'url', '')

        if attachment_type in (KnowledgeAttachment.TYPE_FILE, KnowledgeAttachment.TYPE_IMAGE) and not file_value:
            raise serializers.ValidationError({'file': 'File is required for file/image attachments.'})
        if attachment_type in (KnowledgeAttachment.TYPE_LINK, KnowledgeAttachment.TYPE_VIDEO) and not str(url_value or '').strip():
            raise serializers.ValidationError({'url': 'URL is required for link/video attachments.'})
        return attrs


class KnowledgeQuestionSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='test.title', read_only=True)

    class Meta:
        model = KnowledgeQuestion
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if not request or not is_erp_admin(request.user):
            data.pop('correct_answer', None)
            data.pop('explanation', None)
        return data


class KnowledgeQuestionPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeQuestion
        fields = ('id', 'question_text', 'question_type', 'options', 'points', 'sort_order')


class KnowledgeTestSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    article_title = serializers.CharField(source='article.title', read_only=True)
    questions_count = serializers.IntegerField(read_only=True)
    max_points = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    questions = KnowledgeQuestionPublicSerializer(many=True, read_only=True)

    class Meta:
        model = KnowledgeTest
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')


class KnowledgeTestAttemptSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='test.title', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = KnowledgeTestAttempt
        fields = '__all__'
        read_only_fields = (
            'user',
            'status',
            'score_points',
            'max_points',
            'score_percent',
            'is_passed',
            'started_at',
            'submitted_at',
            'created_at',
            'updated_at',
        )


class ArticleReadLogSerializer(serializers.ModelSerializer):
    article_title = serializers.CharField(source='article.title', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = ArticleReadLog
        fields = '__all__'
        read_only_fields = ('read_count', 'last_read_at', 'created_at', 'updated_at')


class KnowledgeArticleSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    attachments_count = serializers.IntegerField(read_only=True)
    tests_count = serializers.IntegerField(read_only=True)
    attachments = KnowledgeAttachmentSerializer(many=True, read_only=True)
    tests = KnowledgeTestSerializer(many=True, read_only=True)

    class Meta:
        model = KnowledgeArticle
        fields = '__all__'
        read_only_fields = ('author', 'updated_by', 'views_count', 'published_at', 'created_at', 'updated_at')
