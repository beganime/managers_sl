# documents/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from .models import InfoSnippet, ContractTemplate, Contract

@admin.register(InfoSnippet)
class InfoSnippetAdmin(ModelAdmin):
    list_display = ("title", "category", "preview", "copy_btn")
    list_filter = ("category",)
    
    @display(description="Текст")
    def preview(self, obj): 
        return obj.content[:40] + "..." if obj.content else "—"

    @display(description="Копировать", label=True)
    def copy_btn(self, obj):
        # Экранируем текст для безопасного использования в JS
        clean_text = obj.content.replace('"', '&quot;').replace("'", "\\'").replace('\n', ' ')
        # Исправлено: передаем аргумент в format_html вторым параметром
        return format_html(
            '<button type="button" class="bg-primary-600 text-white px-2 py-1 rounded text-xs" '
            'onclick="navigator.clipboard.writeText(\'{}\').then(()=>alert(\'Скопировано!\'))">'
            '📋 Копировать</button>',
            clean_text
        )

@admin.register(ContractTemplate)
class ContractTemplateAdmin(ModelAdmin):
    list_display = ("title", "type", "file")

@admin.register(Contract)
class ContractAdmin(ModelAdmin):
    list_display = ("client", "template", "manager", "status_badge", "download_link")
    list_filter = ("status", "template__type", "manager")
    actions = ["approve_docs"]
    
    fieldsets = (
        ("Основное", {
            "fields": ("client", "template", "program", "manager"),
            "classes": ("tab-tabular",),
        }),
        ("Финансы и Сроки", {
            "fields": (("custom_price", "payment_deadline"),),
            "classes": ("tab-tabular",),
        }),
        ("Данные Заказчика (Если отличается от Студента)", {
            "fields": ("customer_fio", ("customer_passport", "customer_issued_at"), "customer_address"),
            "classes": ("collapse", "!bg-gray-50"),
            "description": "Заполните эти поля, если договор заключается на Родителя. Если оставить пустым - подставятся данные Студента."
        }),
        ("Результат", {
            "fields": ("status", "generated_file"),
        })
    )

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser: return ()
        return ("status", "generated_file", "manager")

    def save_model(self, request, obj, form, change):
        if not obj.pk: 
            obj.manager = request.user
        super().save_model(request, obj, form, change)

    @action(description="✅ Одобрить и создать файлы")
    def approve_docs(self, request, queryset):
        if not request.user.is_superuser:
            return self.message_user(request, "Нет прав", messages.ERROR)
        
        for c in queryset:
            try:
                c.generate_document()
            except Exception as e:
                self.message_user(request, f"Ошибка {c}: {e}", messages.ERROR)
        self.message_user(request, "Готово!", messages.SUCCESS)

    @display(description="Статус", label=True)
    def status_badge(self, obj):
        colors = {'draft': 'warning', 'approved': 'success', 'rejected': 'danger'}
        return obj.get_status_display(), colors.get(obj.status, 'default')

    @display(description="Скачать")
    def download_link(self, obj):
        if obj.generated_file:
            return format_html('<a href="{}" class="text-blue-600 font-bold" target="_blank">📥 Скачать</a>', obj.generated_file.url)
        return "—"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(manager=request.user)