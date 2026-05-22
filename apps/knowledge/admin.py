from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    ArticleReadLog,
    KnowledgeArticle,
    KnowledgeAttachment,
    KnowledgeCategory,
    KnowledgeQuestion,
    KnowledgeTest,
    KnowledgeTestAttempt,
)


class KnowledgeAttachmentInline(TabularInline):
    model = KnowledgeAttachment
    extra = 0
    fields = ('title', 'attachment_type', 'file', 'url', 'sort_order')


class KnowledgeQuestionInline(TabularInline):
    model = KnowledgeQuestion
    extra = 0
    fields = ('question_text', 'question_type', 'points', 'is_active', 'sort_order')


@admin.register(KnowledgeCategory)
class KnowledgeCategoryAdmin(ModelAdmin):
    list_display = ('name', 'code', 'company', 'parent', 'is_public', 'is_active', 'sort_order')
    list_filter = ('is_active', 'is_public', 'company')
    search_fields = ('name', 'code', 'description', 'company__name')
    autocomplete_fields = ('company', 'parent', 'created_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(ModelAdmin):
    list_display = ('title', 'category', 'company', 'office', 'status', 'is_featured', 'is_public', 'published_at')
    list_filter = ('status', 'is_active', 'is_public', 'is_featured', 'company', 'office', 'category')
    search_fields = ('title', 'slug', 'summary', 'content', 'category__name', 'company__name')
    autocomplete_fields = ('company', 'office', 'category', 'author', 'updated_by')
    readonly_fields = ('views_count', 'published_at', 'created_at', 'updated_at')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'published_at'
    inlines = [KnowledgeAttachmentInline]

    @admin.action(description='Publish selected articles')
    def publish_articles(self, request, queryset):
        for article in queryset:
            article.publish(user=request.user)

    @admin.action(description='Archive selected articles')
    def archive_articles(self, request, queryset):
        for article in queryset:
            article.archive(user=request.user)

    actions = ('publish_articles', 'archive_articles')


@admin.register(KnowledgeAttachment)
class KnowledgeAttachmentAdmin(ModelAdmin):
    list_display = ('title', 'article', 'attachment_type', 'uploaded_by', 'sort_order', 'created_at')
    list_filter = ('attachment_type', 'created_at')
    search_fields = ('title', 'url', 'note', 'article__title', 'uploaded_by__email')
    autocomplete_fields = ('article', 'uploaded_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(KnowledgeTest)
class KnowledgeTestAdmin(ModelAdmin):
    list_display = ('title', 'article', 'company', 'office', 'pass_percent', 'is_required', 'is_public', 'is_active')
    list_filter = ('is_active', 'is_required', 'is_public', 'company', 'office')
    search_fields = ('title', 'description', 'article__title', 'company__name')
    autocomplete_fields = ('company', 'office', 'article', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [KnowledgeQuestionInline]


@admin.register(KnowledgeQuestion)
class KnowledgeQuestionAdmin(ModelAdmin):
    list_display = ('test', 'question_type', 'points', 'is_active', 'sort_order')
    list_filter = ('question_type', 'is_active', 'test')
    search_fields = ('question_text', 'test__title')
    autocomplete_fields = ('test',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(KnowledgeTestAttempt)
class KnowledgeTestAttemptAdmin(ModelAdmin):
    list_display = ('test', 'user', 'status', 'score_percent', 'is_passed', 'submitted_at', 'created_at')
    list_filter = ('status', 'is_passed', 'submitted_at', 'created_at')
    search_fields = ('test__title', 'user__email', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('test', 'user')
    readonly_fields = (
        'score_points',
        'max_points',
        'score_percent',
        'is_passed',
        'started_at',
        'submitted_at',
        'created_at',
        'updated_at',
    )


@admin.register(ArticleReadLog)
class ArticleReadLogAdmin(ModelAdmin):
    list_display = ('article', 'user', 'read_count', 'last_read_at')
    list_filter = ('last_read_at', 'created_at')
    search_fields = ('article__title', 'user__email', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('article', 'user')
    readonly_fields = ('read_count', 'last_read_at', 'created_at', 'updated_at')
