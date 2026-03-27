import json
from datetime import timedelta

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from unfold.admin import ModelAdmin
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import action, display

from .models import Task


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
            return queryset.filter(status__in=['todo', 'process'], deadline__lte=tomorrow).order_by('deadline')
        return queryset


@admin.register(Task)
class TaskAdmin(ModelAdmin):
    actions_list = ["open_kanban_view"]

    list_display = (
        "title",
        "pin_badge",
        "client",
        "assigned_to",
        "status_badge",
        "priority_badge",
        "deadline_fmt",
    )
    list_filter = (HotTaskFilter, "is_pinned", "status", "priority", "assigned_to")
    search_fields = ("title", "description", "client__full_name")
    autocomplete_fields = ["assigned_to", "created_by", "client"]

    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (None, {
                "fields": ("title", "description"),
                "classes": ("mb-6",),
            }),
            (_("Связи и Параметры"), {
                "fields": (
                    "client",
                    ("assigned_to", "deadline"),
                    ("status", "priority", "is_pinned"),
                ),
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

    @display(description="PIN", label=True)
    def pin_badge(self, obj):
        return ('Закреплена', 'purple') if obj.is_pinned else ('Обычная', 'gray')

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

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('kanban/', self.admin_site.admin_view(self.kanban_view), name='task_kanban'),
            path('api/update_status/', self.admin_site.admin_view(self.update_task_status), name='task_update_status'),
        ]
        return my_urls + urls

    def kanban_view(self, request):
        tasks = self.get_queryset(request).select_related('assigned_to', 'client')

        context = dict(
            self.admin_site.each_context(request),
            columns={
                "todo": tasks.filter(status='todo'),
                "process": tasks.filter(status='process'),
                "review": tasks.filter(status='review'),
                "done": tasks.filter(status='done'),
            },
            title="Задачи (Канбан)",
        )
        return render(request, "admin/tasks/task/kanban.html", context)

    @csrf_exempt
    def update_task_status(self, request):
        if request.method == "POST":
            try:
                data = json.loads(request.body)
                task = get_object_or_404(Task, id=data.get("task_id"))

                if request.user.is_superuser or task.assigned_to == request.user or task.created_by == request.user:
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
            return qs.select_related('client', 'assigned_to', 'created_by')
        return qs.filter(models.Q(assigned_to=request.user) | models.Q(created_by=request.user)).select_related(
            'client',
            'assigned_to',
            'created_by',
        )
