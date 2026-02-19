from django.contrib import admin
from django.db import models
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import Service

@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    search_fields = ("title", "description")
    list_filter = ("is_active",)
    
    # Виджет для красивого описания
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

    # --- ЛОГИКА СКРЫТИЯ (SECURITY) ---

    def get_list_display(self, request):
        """
        Управляет колонками в таблице.
        Если Админ - показываем Себестоимость.
        Если Менеджер - скрываем.
        """
        base_list = ["title", "display_price_client", "is_active"]
        
        if request.user.is_superuser:
            # Вставляем себестоимость перед статусом
            return base_list[:-1] + ["display_real_cost"] + base_list[-1:]
        
        return base_list

    def get_fieldsets(self, request, obj=None):
        """
        Управляет полями внутри карточки.
        Скрываем блок "Себестоимость" от обычных смертных.
        """
        # Общие поля для всех
        fieldsets = [
            ("Название", {
                "fields": ("title", "is_active"),
                "classes": ("tab-tabular",),
            }),
            ("Информация", {
                "fields": ("description",),
                "classes": ("collapse",),
            }),
            ("Прайс-лист", {
                "fields": ("price_client",),
                "classes": ("tab-tabular",),
            }),
        ]

        # Секретный блок только для Башлыка
        if request.user.is_superuser:
            fieldsets.append(
                ("Финансовая тайна (Себестоимость)", {
                    "fields": ("real_cost",),
                    "classes": ("tab-tabular", "!bg-red-50"), # Подсветка красным фоном
                    "description": "Эту секцию видят только администраторы."
                })
            )
        
        return fieldsets

    # --- ВИЗУАЛИЗАЦИЯ ---

    @display(description="Цена (Клиент)", label=True)
    def display_price_client(self, obj):
        return f"${obj.price_client}", "success" # Зеленый бейдж

    @display(description="Себестоимость", label=True)
    def display_real_cost(self, obj):
        return f"${obj.real_cost}", "danger" # Красный бейдж