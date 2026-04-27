# documents/admin.py
import json

from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action, display

from .models import (
    DocumentReview,
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
from .review_guard import has_document_review_table, safe_get_document_review
from .watermarking import build_approved_document


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser
            or user.is_staff
            or getattr(user, 'role', None) == 'admin'
        )
    )


class KnowledgeSectionAttachmentInline(TabularInline):
    model = KnowledgeSectionAttachment
    extra = 1
    fields = (
        'title',
        'attachment_type',
        'file',
        'url',
        'note',
        'order',
    )


@admin.register(KnowledgeSection)
class KnowledgeSectionAdmin(ModelAdmin):
    list_display = (
        'title',
        'parent',
        'responsibles_display',
        'is_active',
        'order',
        'updated_at',
    )
    list_filter = (
        'is_active',
        'parent',
        'responsible_users',
    )
    search_fields = (
        'title',
        'description',
        'external_url',
        'responsible_users__email',
        'responsible_users__first_name',
        'responsible_users__last_name',
    )
    autocomplete_fields = (
        'parent',
        'responsible_users',
        'created_by',
    )
    filter_horizontal = (
        'responsible_users',
    )
    inlines = [
        KnowledgeSectionAttachmentInline,
    ]

    fieldsets = (
        (
            'Основное',
            {
                'fields': (
                    'parent',
                    'title',
                    'description',
                    ('icon', 'color'),
                    ('order', 'is_active'),
                ),
            },
        ),
        (
            'Файлы и ссылки раздела',
            {
                'fields': (
                    'cover_image',
                    'file',
                    'external_url',
                ),
            },
        ),
        (
            'Ответственные',
            {
                'fields': (
                    'responsible_users',
                ),
            },
        ),
        (
            'Системное',
            {
                'fields': (
                    'slug',
                    'created_by',
                ),
                'classes': (
                    'collapse',
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @display(description='Ответственные')
    def responsibles_display(self, obj):
        users = obj.responsible_users.all()[:3]
        names = []

        for user in users:
            full_name = f'{user.first_name} {user.last_name}'.strip()
            names.append(full_name or user.email)

        return ', '.join(names) if names else '—'


@admin.register(KnowledgeSectionAttachment)
class KnowledgeSectionAttachmentAdmin(ModelAdmin):
    list_display = (
        'title',
        'section',
        'attachment_type',
        'uploaded_by',
        'created_at',
    )
    list_filter = (
        'attachment_type',
        'created_at',
    )
    search_fields = (
        'title',
        'url',
        'note',
        'section__title',
    )
    autocomplete_fields = (
        'section',
        'uploaded_by',
    )

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by_id:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(InfoSnippet)
class InfoSnippetAdmin(ModelAdmin):
    list_display = (
        'title',
        'section',
        'category',
        'content_format',
        'preview',
        'copy_btn',
    )
    list_filter = (
        'category',
        'content_format',
        'section',
    )
    search_fields = (
        'title',
        'content',
        'section__title',
    )
    autocomplete_fields = (
        'section',
    )

    @display(description='Текст')
    def preview(self, obj):
        return (obj.content[:80] + '…') if obj.content else '—'

    @display(description='Копировать', label=True)
    def copy_btn(self, obj):
        clean = (
            obj.content
            .replace('"', '&quot;')
            .replace("'", "\\'")
            .replace('\n', ' ')
        )
        return format_html(
            '<button type="button" class="bg-primary-600 text-white px-2 py-1 rounded text-xs" '
            "onclick=\"navigator.clipboard.writeText('{}').then(()=>alert('Скопировано!'))\">📋</button>",
            clean,
        )


class TestQuestionInline(TabularInline):
    model = TestQuestion
    extra = 1
    fields = (
        'text',
        'options',
        'correct',
        'order',
    )


@admin.register(KnowledgeTest)
class KnowledgeTestAdmin(ModelAdmin):
    list_display = (
        'title',
        'section',
        'questions_count',
        'attempts_count',
        'is_active',
        'updated_at',
    )
    list_filter = (
        'is_active',
        'section',
    )
    search_fields = (
        'title',
        'description',
        'section__title',
    )
    autocomplete_fields = (
        'section',
    )
    inlines = [
        TestQuestionInline,
    ]

    @display(description='Вопросов')
    def questions_count(self, obj):
        return obj.questions.count()

    @display(description='Попыток')
    def attempts_count(self, obj):
        return obj.attempts.count()


@admin.register(KnowledgeTestAttempt)
class KnowledgeTestAttemptAdmin(ModelAdmin):
    list_display = (
        'test',
        'user_display',
        'score_display',
        'percent_display',
        'completed_at',
    )
    list_filter = (
        'test',
        'completed_at',
    )
    search_fields = (
        'test__title',
        'user__email',
        'user__first_name',
        'user__last_name',
    )
    readonly_fields = (
        'test',
        'user',
        'score',
        'total',
        'answers',
        'started_at',
        'completed_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_user(request.user)

    @display(description='Сотрудник')
    def user_display(self, obj):
        full = f'{obj.user.first_name} {obj.user.last_name}'.strip()
        return full or obj.user.email or f'ID {obj.user_id}'

    @display(description='Баллы', label=True)
    def score_display(self, obj):
        return f'{obj.score}/{obj.total}', 'info'

    @display(description='Процент', label=True)
    def percent_display(self, obj):
        percent = obj.percent

        if percent >= 80:
            color = 'success'
        elif percent >= 50:
            color = 'warning'
        else:
            color = 'danger'

        return f'{percent}%', color


class TemplateFieldInline(TabularInline):
    model = TemplateField
    extra = 1
    fields = (
        'key',
        'label',
        'field_type',
        'is_required',
        'order',
    )


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    list_display = (
        'title',
        'is_active',
        'fields_count',
        'updated_at',
    )
    search_fields = (
        'title',
    )
    list_filter = (
        'is_active',
    )
    inlines = [
        TemplateFieldInline,
    ]

    @display(description='Полей')
    def fields_count(self, obj):
        return obj.fields.count()


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(ModelAdmin):
    change_form_template = 'admin/documents/generateddocument/change_form.html'

    list_display = (
        'title',
        'template',
        'deal',
        'manager',
        'status_badge',
        'download_link',
        'created_at',
    )
    list_filter = (
        'status',
        'template',
        'manager',
    )
    search_fields = (
        'title',
        'manager__email',
        'manager__first_name',
        'manager__last_name',
        'deal__client__full_name',
    )
    actions = [
        'approve_documents',
        'regenerate_docs',
    ]

    def get_queryset(self, request):
        related_fields = [
            'template',
            'manager',
            'deal',
            'deal__client',
        ]

        if has_document_review_table():
            related_fields.append('review')

        qs = super().get_queryset(request).select_related(*related_fields)

        if is_admin_user(request.user):
            return qs

        return qs.filter(manager=request.user)

    def get_readonly_fields(self, request, obj=None):
        return (
            'status',
            'generated_file',
            'approved_by',
            'approved_at',
        )

    def _reset_review_after_regenerate(self, doc):
        if not has_document_review_table():
            return

        review, _ = DocumentReview.objects.get_or_create(document=doc)

        if review.approved_file:
            review.approved_file.delete(save=False)

        review.approved_file = None
        review.status = 'pending'
        review.rejection_reason = ''
        review.reviewed_by = None
        review.reviewed_at = None
        review.save()

    @action(description='✅ Одобрить документы')
    def approve_documents(self, request, queryset):
        if not is_admin_user(request.user):
            self.message_user(request, 'Нет прав для этой операции.', messages.ERROR)
            return

        if not has_document_review_table():
            self.message_user(
                request,
                'Таблица documents_documentreview не создана. Сначала примените миграции documents.',
                messages.ERROR,
            )
            return

        count = 0

        for doc in queryset:
            if doc.status != 'generated' or not doc.generated_file:
                continue

            approved_file = build_approved_document(doc)

            if approved_file is None:
                self.message_user(
                    request,
                    f'Ошибка #{doc.id}: не удалось собрать approved-файл с watermark. Проверь DOCUMENT_WATERMARK_IMAGE.',
                    messages.ERROR,
                )
                continue

            review, _ = DocumentReview.objects.get_or_create(document=doc)

            with transaction.atomic():
                if review.approved_file:
                    review.approved_file.delete(save=False)

                review.mark_approved(user=request.user, approved_file=approved_file)

                doc.status = 'approved'
                doc.approved_by = request.user
                doc.approved_at = timezone.now()
                doc.save(
                    update_fields=[
                        'status',
                        'approved_by',
                        'approved_at',
                        'updated_at',
                    ]
                )

            count += 1

        self.message_user(request, f'Одобрено документов: {count}.', messages.SUCCESS)

    @action(description='🔄 Перегенерировать файл')
    def regenerate_docs(self, request, queryset):
        ok = 0
        err = 0

        for doc in queryset:
            if not is_admin_user(request.user) and doc.manager_id != request.user.id:
                continue

            success, msg = doc.generate_document()

            if success:
                self._reset_review_after_regenerate(doc)
                ok += 1
            else:
                err += 1
                self.message_user(request, f'Ошибка #{doc.id}: {msg}', messages.ERROR)

        if ok:
            self.message_user(request, f'Перегенерировано: {ok}.', messages.SUCCESS)

        if err and not ok:
            self.message_user(request, f'Ошибок: {err}.', messages.ERROR)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, 'manager', None):
            if obj.deal_id and obj.deal:
                obj.manager = obj.deal.manager
            else:
                obj.manager = request.user

        super().save_model(request, obj, form, change)

        success, msg = obj.generate_document()

        if success:
            if has_document_review_table():
                self._reset_review_after_regenerate(obj)
            else:
                self.message_user(
                    request,
                    'Документ сгенерирован, но review-таблица ещё не создана. Примените миграции documents.',
                    messages.WARNING,
                )

        level = messages.SUCCESS if success else messages.WARNING
        self.message_user(request, msg, level)

    def get_templates_config(self):
        templates = DocumentTemplate.objects.filter(is_active=True).prefetch_related('fields')
        config = {}

        for template in templates:
            config[template.id] = [
                {
                    'key': field.key,
                    'label': field.label,
                    'field_type': field.field_type,
                    'is_required': field.is_required,
                }
                for field in template.fields.all()
            ]

        return json.dumps(config)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['templates_config_json'] = self.get_templates_config()
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['templates_config_json'] = self.get_templates_config()
        return super().add_view(request, form_url, extra_context)

    @display(description='Статус', label=True)
    def status_badge(self, obj):
        review = safe_get_document_review(obj)
        current_status = review.status if review else obj.status

        colors = {
            'draft': 'warning',
            'generated': 'info',
            'pending': 'info',
            'approved': 'success',
            'rejected': 'danger',
            'error': 'danger',
        }

        labels = {
            'draft': 'Создан / Ожидает',
            'generated': 'Сгенерирован',
            'pending': 'На рассмотрении',
            'approved': 'Одобрен',
            'rejected': 'Отклонён',
            'error': 'Ошибка',
        }

        return labels.get(current_status, obj.get_status_display()), colors.get(current_status, 'default')

    @display(description='Скачать')
    def download_link(self, obj):
        review = safe_get_document_review(obj)

        if review and review.status == 'approved' and review.approved_file:
            return format_html(
                '<a href="{}" class="text-blue-600 font-bold" target="_blank">📥 Скачать</a>',
                review.approved_file.url,
            )

        if obj.status == 'generated':
            return format_html(
                '<span class="text-yellow-600 text-xs">{}</span>',
                '⏳ Ожидает одобрения',
            )

        return '—'