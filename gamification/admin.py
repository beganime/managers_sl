from django.contrib import admin
from django.db import models
from django.utils.html import format_html, mark_safe
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import Notification, TutorialVideo, RatingSnapshot, Leaderboard

# --- УВЕДОМЛЕНИЯ ---
@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("title", "recipient", "is_read_badge", "created_at")
    list_filter = ("is_read",)
    
    # Каждый видит только свои уведомления
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(recipient=request.user)

    @display(description="Прочитано", boolean=True)
    def is_read_badge(self, obj):
        return obj.is_read

# --- ВИДЕО ---
@admin.register(TutorialVideo)
class TutorialVideoAdmin(ModelAdmin):
    list_display = ("title", "display_source", "created_at")
    search_fields = ("title",)
    
    formfield_overrides = {models.TextField: {"widget": WysiwygWidget}}

    @display(description="Источник")
    def display_source(self, obj):
        return "📁 Файл" if obj.video_file else ("🔗 YouTube" if obj.youtube_url else "—")

# --- ЖИВОЙ РЕЙТИНГ (LEADERBOARD) ---
@admin.register(Leaderboard)
class LeaderboardAdmin(ModelAdmin):
    list_display = ("display_rank", "display_manager", "display_office", "display_revenue")
    list_display_links = None # Отключаем кликабельность (только просмотр)
    search_fields = ("first_name", "last_name")
    list_filter = ("office",)

    # Показываем ВСЕХ менеджеров ВСЕМ пользователям
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Фильтруем только тех, у кого есть профиль зарплаты (менеджеров)
        return qs.filter(managersalary__isnull=False).order_by('-managersalary__current_month_revenue')

    # Запрещаем любые действия кроме просмотра
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    # --- ВИЗУАЛ ---

    @display(description="Место", label=True)
    def display_rank(self, obj):
        """Вычисляет место на лету"""
        # Считаем, сколько людей заработали больше меня
        my_revenue = obj.managersalary.current_month_revenue
        rank = Leaderboard.objects.filter(managersalary__current_month_revenue__gt=my_revenue).count() + 1
        
        if rank == 1: return f"🥇 1", "warning"
        if rank == 2: return f"🥈 2", "default"
        if rank == 3: return f"🥉 3", "error"
        return f"#{rank}", "info"

    @display(description="Менеджер")
    def display_manager(self, obj):
        """Красивый вывод с аватаркой (Исправлено format_html)"""
        avatar_html = ""
        if obj.avatar:
            avatar_html = f'<img src="{obj.avatar.url}" style="width: 30px; height: 30px; border-radius: 50%; margin-right: 10px; object-fit: cover;">'
        else:
            avatar_html = '<div style="width: 30px; height: 30px; border-radius: 50%; background: #ccc; margin-right: 10px; display: inline-block;"></div>'
        
        # Используем format_html правильно: строка формата + аргументы
        return format_html(
            '<div style="display: flex; align-items: center;">{} {} {}</div>',
            mark_safe(avatar_html),
            obj.first_name,
            obj.last_name
        )

    @display(description="Офис")
    def display_office(self, obj):
        return obj.office.city if obj.office else "-"

    @display(description="Выручка (Месяц)", label=True)
    def display_revenue(self, obj):
        val = obj.managersalary.current_month_revenue
        return f"${val:,.2f}", "success"

# --- АРХИВ РЕЙТИНГОВ ---
@admin.register(RatingSnapshot)
class RatingSnapshotAdmin(ModelAdmin):
    list_display = ("period", "top_office_display", "gold_medal_manager", "created_at_fmt")
    
    fieldsets = (
        ("Период", {"fields": ("period", "top_office", "top_office_revenue"), "classes": ("tab-tabular",)}),
        ("Топ-3", {
            "fields": (
                ("first_place_manager", "first_place_revenue"),
                ("second_place_manager", "second_place_revenue"),
                ("third_place_manager", "third_place_revenue"),
            ),
            "classes": ("!bg-yellow-50",),
        }),
    )

    @display(description="Дата")
    def created_at_fmt(self, obj):
        return obj.period.end_date

    @display(description="Топ Офис", label=True)
    def top_office_display(self, obj):
        return f"🏆 {obj.top_office}", "warning"

    @display(description="1 Место 🥇")
    def gold_medal_manager(self, obj):
        return f"{obj.first_place_manager} (${obj.first_place_revenue})" if obj.first_place_manager else "-"