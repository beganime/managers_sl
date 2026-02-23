# tasks/admin.py
import json
from django.contrib import admin
from django.db import models
from django.urls import path
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta
from django.contrib.admin import SimpleListFilter

from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from unfold.contrib.forms.widgets import WysiwygWidget

from .models import Task

# КАСТОМНЫЙ ФИЛЬТР: "Горящие задачи"
class HotTaskFilter(SimpleListFilter):
    title = "Горящие задачи 🔥"
    parameter_name = "is_hot"

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Горят (Дедлайн в течение 24ч)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            now = timezone.now()
            tomorrow = now + timedelta(days=1)
            # Отдаем задачи, которые не сделаны и срок подходит к концу
            return queryset.filter(status__in=['todo', 'process'], deadline__lte=tomorrow).order_by('deadline')
        return queryset


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    actions_list = ["open_kanban_view"]

    list_display = ("title", "assigned_to", "status_badge", "priority_badge", "deadline_fmt")
    # Добавили наш кастомный фильтр HotTaskFilter
    list_filter = (HotTaskFilter, "status", "priority", "assigned_to")
    search_fields = ("title", "description")

    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                "fields": ("title", "description"),
                "classes": ("mb-6",),
            }),
            (_("Параметры выполнения"), {
                "fields": (("assigned_to", "deadline"), ("status", "priority")),
            }),
        ]
        
        if request.user.is_superuser:
            fieldsets.append(
                (_("Системное"), {
                    "fields": ("created_by",),
                    "classes": ("collapse",),
                })
            )
        return fieldsets

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @display(description="Статус", label=True)
    def status_badge(self, obj):
        colors = {'todo': 'gray', 'process': 'blue', 'review': 'orange', 'done': 'green'}
        return obj.get_status_display(), colors.get(obj.status, 'gray')

    @display(description="Приоритет", label=True)
    def priority_badge(self, obj):
        colors = {'low': 'green', 'medium': 'yellow', 'high': 'red'}
        return obj.get_priority_display(), colors.get(obj.priority, 'gray')

    @display(description="Дедлайн")
    def deadline_fmt(self, obj):
        return obj.deadline.strftime("%d.%m %H:%M") if obj.deadline else "—"

    # --- КАНБАН ---
    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('kanban/', self.admin_site.admin_view(self.kanban_view), name='task_kanban'),
            path('api/update_status/', self.admin_site.admin_view(self.update_task_status), name='task_update_status'),
        ]
        return my_urls + urls

    def kanban_view(self, request):
        tasks = self.get_queryset(request).select_related('assigned_to')

        context = dict(
            self.admin_site.each_context(request),
            columns={
                "todo": tasks.filter(status='todo'),
                "process": tasks.filter(status='process'),
                "review": tasks.filter(status='review'),
                "done": tasks.filter(status='done'),
            },
            title="Задачи (Канбан)"
        )
        return render(request, "admin/tasks/task/kanban.html", context)

    @csrf_exempt
    def update_task_status(self, request):
        if request.method == "POST":
            try:
                data = json.loads(request.body)
                task = get_object_or_404(Task, id=data.get("task_id"))
                
                if request.user.is_superuser or task.assigned_to == request.user:
                    task.status = data.get("status")
                    task.save()
                    return JsonResponse({"success": True})
                return JsonResponse({"error": "Нет прав"}, status=403)
            except Exception as e:
                return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"error": "Method not allowed"}, status=405)

    @action(description="📋 Открыть Канбан", url_path="kanban")
    def open_kanban_view(self, request):
        pass
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(models.Q(assigned_to=request.user) | models.Q(created_by=request.user))