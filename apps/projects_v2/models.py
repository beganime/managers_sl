from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import ActiveModel, OrderedModel, TimeStampedModel
from apps.organizations.models import Company, Office


class Project(TimeStampedModel, ActiveModel):
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_DONE = 'done'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_DONE, 'Done'),
        (STATUS_ARCHIVED, 'Archived'),
    )

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='projects_v2')
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='projects_v2',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, db_index=True)
    code = models.SlugField('Code', max_length=100, blank=True, db_index=True)
    description = models.TextField('Description', blank=True)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    deadline = models.DateTimeField('Deadline', null=True, blank=True)
    is_pinned = models.BooleanField('Pinned', default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='projects_v2_created',
        null=True,
        blank=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Owner',
        on_delete=models.SET_NULL,
        related_name='projects_v2_owned',
        null=True,
        blank=True,
    )
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name='Participants', blank=True, related_name='projects_v2_participating')
    responsible_users = models.ManyToManyField(settings.AUTH_USER_MODEL, verbose_name='Responsible users', blank=True, related_name='projects_v2_responsible')
    custom_data = models.JSONField('Custom data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Project v2'
        verbose_name_plural = 'Projects v2'
        ordering = ['-is_pinned', '-updated_at']
        unique_together = [('company', 'code')]
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['owner', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title

    @property
    def tasks_count(self):
        return self.tasks.count()

    @property
    def completed_tasks_count(self):
        return self.tasks.filter(status=ProjectTask.STATUS_DONE).count()

    @property
    def progress_percent(self):
        total = self.tasks_count
        if total <= 0:
            return 100 if self.status == self.STATUS_DONE else 0
        return round((self.completed_tasks_count / total) * 100)


class ProjectSection(TimeStampedModel, ActiveModel, OrderedModel):
    project = models.ForeignKey(Project, verbose_name='Project', on_delete=models.CASCADE, related_name='sections')
    title = models.CharField('Title', max_length=255)
    description = models.TextField('Description', blank=True)
    color = models.CharField('Color', max_length=32, blank=True)

    class Meta:
        verbose_name = 'Project section'
        verbose_name_plural = 'Project sections'
        ordering = ['project__title', 'sort_order', 'title']
        unique_together = [('project', 'title')]
        indexes = [
            models.Index(fields=['project', 'is_active']),
            models.Index(fields=['sort_order']),
        ]

    def __str__(self):
        return f'{self.project}: {self.title}'


class ProjectTask(TimeStampedModel, OrderedModel):
    STATUS_TODO = 'todo'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_REVIEW = 'review'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = (
        (STATUS_TODO, 'To do'),
        (STATUS_IN_PROGRESS, 'In progress'),
        (STATUS_REVIEW, 'Review'),
        (STATUS_DONE, 'Done'),
        (STATUS_CANCELLED, 'Cancelled'),
    )

    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_URGENT = 'urgent'
    PRIORITY_CHOICES = (
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    )

    project = models.ForeignKey(Project, verbose_name='Project', on_delete=models.CASCADE, related_name='tasks')
    section = models.ForeignKey(
        ProjectSection,
        verbose_name='Section',
        on_delete=models.SET_NULL,
        related_name='tasks',
        null=True,
        blank=True,
    )
    parent = models.ForeignKey(
        'self',
        verbose_name='Parent task',
        on_delete=models.CASCADE,
        related_name='subtasks',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, db_index=True)
    description = models.TextField('Description', blank=True)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_TODO, db_index=True)
    priority = models.CharField('Priority', max_length=32, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Assigned to',
        on_delete=models.SET_NULL,
        related_name='projects_v2_tasks_assigned',
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='projects_v2_tasks_created',
        null=True,
        blank=True,
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Completed by',
        on_delete=models.SET_NULL,
        related_name='projects_v2_tasks_completed',
        null=True,
        blank=True,
    )
    deadline = models.DateTimeField('Deadline', null=True, blank=True)
    completed_at = models.DateTimeField('Completed at', null=True, blank=True)
    custom_data = models.JSONField('Custom data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Project task v2'
        verbose_name_plural = 'Project tasks v2'
        ordering = ['project__title', 'section__sort_order', 'sort_order', '-updated_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['section', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['deadline']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_DONE and not self.completed_at:
            self.completed_at = timezone.now()
        if self.status != self.STATUS_DONE:
            self.completed_at = None
            self.completed_by = None
        super().save(*args, **kwargs)

    def complete(self, user=None):
        self.status = self.STATUS_DONE
        self.completed_by = user
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_by', 'completed_at', 'updated_at'])
        return self

    def reopen(self):
        self.status = self.STATUS_TODO
        self.completed_by = None
        self.completed_at = None
        self.save(update_fields=['status', 'completed_by', 'completed_at', 'updated_at'])
        return self


class TaskComment(TimeStampedModel):
    task = models.ForeignKey(ProjectTask, verbose_name='Task', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Author', on_delete=models.SET_NULL, related_name='projects_v2_comments', null=True, blank=True)
    text = models.TextField('Text')

    class Meta:
        verbose_name = 'Task comment'
        verbose_name_plural = 'Task comments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', 'created_at']),
            models.Index(fields=['author', 'created_at']),
        ]

    def __str__(self):
        return f'{self.task}: {self.author}'


class TaskChecklist(TimeStampedModel, OrderedModel):
    task = models.ForeignKey(ProjectTask, verbose_name='Task', on_delete=models.CASCADE, related_name='checklists')
    title = models.CharField('Title', max_length=255)

    class Meta:
        verbose_name = 'Task checklist'
        verbose_name_plural = 'Task checklists'
        ordering = ['task__title', 'sort_order', 'title']
        indexes = [
            models.Index(fields=['task', 'sort_order']),
        ]

    def __str__(self):
        return f'{self.task}: {self.title}'

    @property
    def items_count(self):
        return self.items.count()

    @property
    def completed_items_count(self):
        return self.items.filter(is_done=True).count()


class TaskChecklistItem(TimeStampedModel, OrderedModel):
    checklist = models.ForeignKey(TaskChecklist, verbose_name='Checklist', on_delete=models.CASCADE, related_name='items')
    title = models.CharField('Title', max_length=255)
    is_done = models.BooleanField('Done', default=False, db_index=True)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Done by',
        on_delete=models.SET_NULL,
        related_name='projects_v2_checklist_items_done',
        null=True,
        blank=True,
    )
    done_at = models.DateTimeField('Done at', null=True, blank=True)

    class Meta:
        verbose_name = 'Task checklist item'
        verbose_name_plural = 'Task checklist items'
        ordering = ['checklist__title', 'sort_order', 'title']
        indexes = [
            models.Index(fields=['checklist', 'is_done']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.is_done and not self.done_at:
            self.done_at = timezone.now()
        if not self.is_done:
            self.done_at = None
            self.done_by = None
        super().save(*args, **kwargs)


class TaskAttachment(models.Model):
    TYPE_FILE = 'file'
    TYPE_IMAGE = 'image'
    TYPE_LINK = 'link'
    TYPE_CHOICES = (
        (TYPE_FILE, 'File'),
        (TYPE_IMAGE, 'Image'),
        (TYPE_LINK, 'Link'),
    )

    task = models.ForeignKey(ProjectTask, verbose_name='Task', on_delete=models.CASCADE, related_name='attachments')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Uploaded by',
        on_delete=models.SET_NULL,
        related_name='projects_v2_attachments',
        null=True,
        blank=True,
    )
    title = models.CharField('Title', max_length=255, blank=True)
    attachment_type = models.CharField('Attachment type', max_length=32, choices=TYPE_CHOICES, default=TYPE_FILE)
    file = models.FileField('File', upload_to='erp/projects_v2/task_attachments/', null=True, blank=True)
    url = models.URLField('URL', max_length=1000, blank=True)
    note = models.TextField('Note', blank=True)
    created_at = models.DateTimeField('Created at', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Task attachment'
        verbose_name_plural = 'Task attachments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', 'created_at']),
            models.Index(fields=['uploaded_by', 'created_at']),
        ]

    def __str__(self):
        return self.title or self.url or f'Attachment #{self.pk}'


class ProjectNote(TimeStampedModel):
    project = models.ForeignKey(Project, verbose_name='Project', on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Author', on_delete=models.SET_NULL, related_name='projects_v2_notes', null=True, blank=True)
    title = models.CharField('Title', max_length=255, blank=True)
    content = models.TextField('Content')
    is_private = models.BooleanField('Private', default=False, db_index=True)
    is_pinned = models.BooleanField('Pinned', default=False)

    class Meta:
        verbose_name = 'Project note'
        verbose_name_plural = 'Project notes'
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['project', 'is_private']),
            models.Index(fields=['author', 'created_at']),
        ]

    def __str__(self):
        return self.title or f'Note #{self.pk}'


class TaskWatcher(models.Model):
    task = models.ForeignKey(ProjectTask, verbose_name='Task', on_delete=models.CASCADE, related_name='watchers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE, related_name='projects_v2_watched_tasks')
    created_at = models.DateTimeField('Created at', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Task watcher'
        verbose_name_plural = 'Task watchers'
        ordering = ['-created_at']
        unique_together = [('task', 'user')]
        indexes = [
            models.Index(fields=['task', 'user']),
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f'{self.user} watches {self.task}'
