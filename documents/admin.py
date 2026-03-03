# documents/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from .models import InfoSnippet, DocumentTemplate, GeneratedDocument

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

@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    list_display = ("title", "is_active", "fields_count", "updated_at")
    search_fields = ("title",)
    list_filter = ("is_active",)

    @display(description="Кол-во динамических полей")
    def fields_count(self, obj):
        if isinstance(obj.fields_config, list):
            return len(obj.fields_config)
        return 0

@admin.register(GeneratedDocument)
class GeneratedDocumentAdmin(ModelAdmin):
    list_display = ("title", "template", "manager", "status_badge", "download_link", "created_at")
    list_filter = ("status", "template", "manager")
    search_fields = ("title", "manager__email", "manager__first_name")
    
    # Чтобы админ случайно не сломал сгенерированный файл
    readonly_fields = ("status", "generated_file", "manager")

    def save_model(self, request, obj, form, change):
        if not obj.pk: 
            obj.manager = request.user
        super().save_model(request, obj, form, change)

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