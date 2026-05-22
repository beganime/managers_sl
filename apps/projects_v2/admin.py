from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Project,
    ProjectNote,
    ProjectSection,
    ProjectTask,
    TaskAttachment,
    TaskChecklist,
    TaskChecklistItem,
    TaskComment,
    TaskWatcher,
)


class ProjectSectionInline(TabularInline):
    model = ProjectSection
    extra = 0
    fields = ('title', 'sort_order', 'is_active')


class TaskChecklistItemInline(TabularInline):
    model = TaskChecklistItem
    extra = 0
    fields = ('title', 'is_done', 'sort_order')


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ('title', 'company', 'office', 'owner', 'status', 'deadline', 'is_pinned', 'is_active')
    list_filter = ('status', 'is_active', 'is_pinned', 'company', 'office')
    search_fields = ('title', 'code', 'description', 'company__name', 'office__name')
    autocomplete_fields = ('company', 'office', 'created_by', 'owner', 'participants', 'responsible_users')
    filter_horizontal = ('participants', 'responsible_users')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    inlines = [ProjectSectionInline]


@admin.register(ProjectSection)
class ProjectSectionAdmin(ModelAdmin):
    list_display = ('title', 'project', 'sort_order', 'is_active')
    list_filter = ('is_active', 'project__company', 'project__office')
    search_fields = ('title', 'description', 'project__title')
    autocomplete_fields = ('project',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProjectTask)
class ProjectTaskAdmin(ModelAdmin):
    list_display = ('title', 'project', 'section', 'assigned_to', 'status', 'priority', 'deadline', 'completed_at')
    list_filter = ('status', 'priority', 'project__company', 'project__office', 'section', 'deadline')
    search_fields = ('title', 'description', 'project__title', 'assigned_to__email')
    autocomplete_fields = ('project', 'section', 'parent', 'assigned_to', 'created_by', 'completed_by')
    readonly_fields = ('completed_at', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    @admin.action(description='Complete selected tasks')
    def complete_tasks(self, request, queryset):
        for task in queryset:
            task.complete(user=request.user)

    @admin.action(description='Reopen selected tasks')
    def reopen_tasks(self, request, queryset):
        for task in queryset:
            task.reopen()

    actions = ('complete_tasks', 'reopen_tasks')


@admin.register(TaskComment)
class TaskCommentAdmin(ModelAdmin):
    list_display = ('task', 'author', 'created_at')
    list_filter = ('created_at', 'task__project__company', 'task__project__office')
    search_fields = ('task__title', 'author__email', 'text')
    autocomplete_fields = ('task', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TaskChecklist)
class TaskChecklistAdmin(ModelAdmin):
    list_display = ('title', 'task', 'sort_order', 'items_count', 'completed_items_count')
    list_filter = ('task__project__company', 'task__project__office')
    search_fields = ('title', 'task__title', 'task__project__title')
    autocomplete_fields = ('task',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [TaskChecklistItemInline]


@admin.register(TaskChecklistItem)
class TaskChecklistItemAdmin(ModelAdmin):
    list_display = ('title', 'checklist', 'is_done', 'done_by', 'done_at', 'sort_order')
    list_filter = ('is_done', 'done_at', 'checklist__task__project__company')
    search_fields = ('title', 'checklist__title', 'checklist__task__title')
    autocomplete_fields = ('checklist', 'done_by')
    readonly_fields = ('done_at', 'created_at', 'updated_at')


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(ModelAdmin):
    list_display = ('title', 'task', 'attachment_type', 'uploaded_by', 'created_at')
    list_filter = ('attachment_type', 'created_at', 'task__project__company')
    search_fields = ('title', 'url', 'note', 'task__title')
    autocomplete_fields = ('task', 'uploaded_by')
    readonly_fields = ('created_at',)


@admin.register(ProjectNote)
class ProjectNoteAdmin(ModelAdmin):
    list_display = ('title', 'project', 'author', 'is_private', 'is_pinned', 'created_at')
    list_filter = ('is_private', 'is_pinned', 'project__company', 'project__office', 'created_at')
    search_fields = ('title', 'content', 'project__title', 'author__email')
    autocomplete_fields = ('project', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TaskWatcher)
class TaskWatcherAdmin(ModelAdmin):
    list_display = ('task', 'user', 'created_at')
    list_filter = ('created_at', 'task__project__company', 'task__project__office')
    search_fields = ('task__title', 'user__email')
    autocomplete_fields = ('task', 'user')
    readonly_fields = ('created_at',)
