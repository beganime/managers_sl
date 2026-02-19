from django.contrib import admin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

@admin.register(LogEntry)
class AuditLogAdmin(ModelAdmin):
    # Настройки отображения
    list_display = ("action_time", "user", "action_flag_badge", "content_type", "object_repr", "change_message")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")
    date_hierarchy = "action_time"
    
    # Сортировка: новые сверху
    ordering = ("-action_time",)

    # Запрещаем любые изменения логов (только просмотр)
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    # Доступ только для Башлыка (Суперюзера)
    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "content_type")

    def has_module_permission(self, request):
        return request.user.is_superuser

    # Красивые бейджики для действий
    @display(description="Действие", label=True)
    def action_flag_badge(self, obj):
        if obj.action_flag == ADDITION:
            return "Создание", "success"
        elif obj.action_flag == CHANGE:
            return "Изменение", "warning"
        elif obj.action_flag == DELETION:
            return "Удаление", "danger"
        return "Другое", "default"

    # Переименование модели в меню
    def get_model_perms(self, request):
        """Скрываем из меню, если не суперюзер (доп. защита)"""
        if not request.user.is_superuser:
            return {}
        return super().get_model_perms(request)
    
    class Meta:
        verbose_name = "История действий"
        verbose_name_plural = "История действий"