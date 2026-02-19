from django.contrib import admin
from django.db import models
from django.db.models import Q 
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline
from unfold.decorators import display
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import Client, ClientRelative

class ClientRelativeInline(StackedInline):
    model = ClientRelative
    verbose_name_plural = "Ближайший родственник / Контактное лицо"
    fields = (('full_name', 'relation_type'), ('phone', 'work_place'))
    extra = 0

@admin.register(Client)
class ClientAdmin(ModelAdmin):
    inlines = [ClientRelativeInline]
    
    list_display = (
        "display_fullname",
        "status_badge",
        "citizenship", # <-- Добавил вывод гражданства в список
        "manager",
        "phone",
        "city",
        "partner_info",
        "created_at"
    )
    
    # Добавил фильтр по Гражданству
    list_filter = ("status", "citizenship", "is_priority", "city", "is_partner_client")
    
    search_fields = ("full_name", "phone", "email", "passport_inter_num", "passport_local_num")
    ordering = ("-created_at",)

    # Включаем поиск для выбора менеджера (чтобы не листать список, если сотрудников много)
    autocomplete_fields = ["manager", "shared_with"]

    fieldsets = (
        (_("Основное"), {
            "fields": (("full_name", "is_priority"), ("status", "manager"), "shared_with"),
            "classes": ("tab-tabular",),
        }),
        (_("Контакты и Личные данные"), {
            "fields": (("phone", "email"), ("city", "dob"), "citizenship"), # <-- Гражданство здесь
            "classes": ("collapse",),
        }),
        (_("Паспорт и Прописка"), { # <-- НОВАЯ СЕКЦИЯ ДЛЯ ДОКУМЕНТОВ
            "fields": (
                ("passport_inter_num", "passport_local_num"),
                ("passport_issued_by", "passport_issued_date"),
                "address_registration"
            ),
            "classes": ("collapse", "!bg-gray-50"), # Выделил серым фоном
        }),
        (_("Партнерство и Финансы"), {
            "fields": (("is_partner_client", "partner_name"), ("has_discount", "discount_amount")),
            "classes": ("collapse",),
        }),
        (_("Рабочий процесс"), {
            "fields": ("current_tasks", "comments"),
            "classes": ("!bg-gray-50",),
        }),
    )

    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

    # --- ГЛАВНАЯ ЛОГИКА ОГРАНИЧЕНИЯ ВИДИМОСТИ ---
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Если Суперюзер - видит всех
        if request.user.is_superuser:
            return qs
        # Если Менеджер - видит Своих + Расшаренных ему
        return qs.filter(
            Q(manager=request.user) | Q(shared_with=request.user)
        ).distinct()

    def save_model(self, request, obj, form, change):
        # Если создаем нового и менеджер не выбран - ставим текущего
        if not obj.pk and not obj.manager_id:
            obj.manager = request.user
        super().save_model(request, obj, form, change)

    # --- ДЕКОРАТОРЫ (Красивое отображение) ---
    @display(description="Клиент", header=True)
    def display_fullname(self, obj):
        icon = "⭐ " if obj.is_priority else ""
        discount_icon = " 🏷️" if obj.has_discount else ""
        return f"{icon}{obj.full_name}{discount_icon}"

    @display(description="Статус", label=True)
    def status_badge(self, obj):
        colors = {
            'new': 'blue',
            'consultation': 'purple', 
            'documents': 'yellow', 
            'visa': 'orange',
            'success': 'green',
            'rejected': 'red',
            'archive': 'gray',
        }
        return obj.get_status_display(), colors.get(obj.status, 'gray')

    @display(description="Партнер", boolean=True)
    def partner_info(self, obj):
        return obj.is_partner_client