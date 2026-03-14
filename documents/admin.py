# documents/admin.py
import json
from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from .models import InfoSnippet, DocumentTemplate, TemplateField, GeneratedDocument

@admin.register(InfoSnippet)
class InfoSnippetAdmin(ModelAdmin):
    list_display = ("title", "category", "preview", "copy_btn")
    list_filter = ("category",)
    
    @display(description="Текст")
    def preview(self, obj): 
        return obj.content[:40] + "..." if obj.content else "—"

    @display(description="Копировать", label=True)
    def copy_btn(self, obj):
        clean_text = obj.content.replace('"', '&quot;').replace("'", "\\'").replace('\n', ' ')
        return format_html(
            '<button type="button" class="bg-primary-600 text-white px-2 py-1 rounded text-xs" '
            'onclick="navigator.clipboard.writeText(\'{}\').then(()=>alert(\'Скопировано!\'))">'
            '📋 Копировать</button>',
            clean_text
        )

class TemplateFieldInline(TabularInline):
    model = TemplateField
    extra = 1
    fields = ('key', 'label', 'field_type', 'is_required', 'order')

@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    list_display = ("title", "is_active", "fields_count", "updated_at")
    search_fields = ("title",)
    list_filter = ("is_active",)
    inlines = [TemplateFieldInline]

    @display(description="Кол-во динамических полей")
    def fields_count(self, obj):
        return obj.fields.count()


@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(ModelAdmin):
    # Указываем кастомный шаблон для формы редактирования/создания
    change_form_template = "admin/documents/generateddocument/change_form.html"
    
    list_display = ("title", "template", "manager", "status_badge", "download_link", "created_at")
    list_filter = ("status", "template", "manager")
    search_fields = ("title", "manager__email", "manager__first_name")
    
    def get_readonly_fields(self, request, obj=None):
        return ("status", "generated_file")

    # Передаем конфигурацию полей шаблонов в HTML-шаблон админки
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['templates_config_json'] = self.get_templates_config()
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['templates_config_json'] = self.get_templates_config()
        return super().add_view(request, form_url, extra_context=extra_context)

    def get_templates_config(self):
        """Возвращает JSON со всеми активными шаблонами и их полями"""
        templates = DocumentTemplate.objects.filter(is_active=True).prefetch_related('fields')
        config = {}
        for t in templates:
            config[t.id] = [
                {
                    'key': f.key,
                    'label': f.label,
                    'field_type': f.field_type,
                    'is_required': f.is_required
                }
                for f in t.fields.all()
            ]
        return json.dumps(config)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, 'manager', None):
            obj.manager = request.user
            
        super().save_model(request, obj, form, change)

        try:
            obj.generate_document()
            self.message_user(request, "Документ успешно сгенерирован!", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Ошибка генерации документа: {e}", messages.ERROR)

    @action(description="🔄 Сгенерировать файл заново")
    def regenerate_docs(self, request, queryset):
        for doc in queryset:
            try:
                doc.generate_document()
            except Exception as e:
                self.message_user(request, f"Ошибка {doc}: {e}", messages.ERROR)
        self.message_user(request, "Документы успешно перегенерированы!", messages.SUCCESS)

    @display(description="Статус", label=True)
    def status_badge(self, obj):
        colors = {'draft': 'warning', 'generated': 'success', 'error': 'danger'}
        return obj.get_status_display(), colors.get(obj.status, 'default')

    @display(description="Скачать")
    def download_link(self, obj):
        if obj.generated_file:
            return format_html('<a href="{}" class="text-blue-600 font-bold" target="_blank">📥 Скачать</a>', obj.generated_file.url)
        return "—"