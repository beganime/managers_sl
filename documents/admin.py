# documents/admin.py
import json

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action

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


@admin.register(InfoSnippet)
class InfoSnippetAdmin(ModelAdmin):
    list_display = ('title', 'category', 'preview', 'copy_btn')
    list_filter = ('category',)
    search_fields = ('title', 'content')

    @display(description="Текст")
    def preview(self, obj):
        return (obj.content[:50] + '…') if obj.content else '—'

    @display(description="Копировать", label=True)
    def copy_btn(self, obj):
        clean = obj.content.replace('"', '&quot;').replace("'", "\\'").replace('\n', ' ')
        return format_html(
            '<button type="button" class="bg-primary-600 text-white px-2 py-1 rounded text-xs" '
            "onclick=\"navigator.clipboard.writeText('{}').then(()=>alert('Скопировано!'))\">📋</button>",
            clean,
        )


class TestQuestionInline(TabularInline):
    model = TestQuestion
    extra = 1
    fields = ('text', 'options', 'correct', 'order')


@admin.register(KnowledgeTest)
class KnowledgeTestAdmin(ModelAdmin):
    list_display = ('title', 'questions_count', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title',)
    inlines = [TestQuestionInline]

    @display(description="Вопросов")
    def questions_count(self, obj):
        return obj.questions.count()


class TemplateFieldInline(TabularInline):
    model = TemplateField
    extra = 1
    fields = ('key', 'label', 'field_type', 'is_required', 'order')


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    list_display = ('title', 'is_active', 'fields_count', 'updated_at')
    search_fields = ('title',)
    list_filter = ('is_active',)
    inlines = [TemplateFieldInline]

    @display(description="Полей")
    def fields_count(self, obj):
        return obj.fields.count()


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(ModelAdmin):
    change_form_template = "admin/documents/generateddocument/change_form.html"

    list_display = (
        'title',
        'template',
        'deal',
        'manager',
        'status_badge',
        'download_link',
        'created_at',
    )
    list_filter = ('status', 'template', 'manager')
    search_fields = ('title', 'manager__email', 'manager__first_name', 'deal__client__full_name')
    actions = ['approve_documents', 'regenerate_docs']

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related('template', 'manager', 'deal', 'deal__client')
        if is_admin_user(request.user):
            return qs
        return qs.filter(manager=request.user)

    def get_readonly_fields(self, request, obj=None):
        return ('status', 'generated_file', 'approved_by', 'approved_at')

    @action(description="✅ Одобрить документы")
    def approve_documents(self, request, queryset):
        if not is_admin_user(request.user):
            self.message_user(request, "Нет прав для этой операции.", messages.ERROR)
            return

        count = 0
        for doc in queryset:
            if doc.status == 'generated' and doc.generated_file:
                doc.status = 'approved'
                doc.approved_by = request.user
                doc.approved_at = timezone.now()
                doc.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
                count += 1

        self.message_user(request, f"Одобрено документов: {count}.", messages.SUCCESS)

    @action(description="🔄 Перегенерировать файл")
    def regenerate_docs(self, request, queryset):
        ok, err = 0, 0
        for doc in queryset:
            if not is_admin_user(request.user) and doc.manager_id != request.user.id:
                continue

            success, msg = doc.generate_document()
            if success:
                ok += 1
            else:
                err += 1
                self.message_user(request, f"Ошибка #{doc.id}: {msg}", messages.ERROR)

        if ok:
            self.message_user(request, f"Перегенерировано: {ok}.", messages.SUCCESS)
        if err and not ok:
            self.message_user(request, f"Ошибок: {err}.", messages.ERROR)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, 'manager', None):
            if obj.deal_id and obj.deal:
                obj.manager = obj.deal.manager
            else:
                obj.manager = request.user

        super().save_model(request, obj, form, change)

        success, msg = obj.generate_document()
        level = messages.SUCCESS if success else messages.WARNING
        self.message_user(request, msg, level)

    def get_templates_config(self):
        templates = DocumentTemplate.objects.filter(is_active=True).prefetch_related('fields')
        config = {}
        for t in templates:
            config[t.id] = [
                {
                    'key': f.key,
                    'label': f.label,
                    'field_type': f.field_type,
                    'is_required': f.is_required,
                }
                for f in t.fields.all()
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

    @display(description="Статус", label=True)
    def status_badge(self, obj):
        colors = {
            'draft': 'warning',
            'generated': 'info',
            'approved': 'success',
            'error': 'danger',
        }
        return obj.get_status_display(), colors.get(obj.status, 'default')

    @display(description="Скачать")
    def download_link(self, obj):
        if obj.can_download:
            return format_html(
                '<a href="{}" class="text-blue-600 font-bold" target="_blank">📥 Скачать</a>',
                obj.generated_file.url,
            )
        if obj.status == 'generated':
            return format_html('<span class="text-yellow-600 text-xs">⏳ Ожидает одобрения</span>')
        return '—'