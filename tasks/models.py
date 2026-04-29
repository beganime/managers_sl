from django.conf import settings
from django.db import models


class Task(models.Model):
    KANBAN_STATUS = (
        ('todo', 'Нужно сделать'),
        ('process', 'В работе'),
        ('review', 'На проверке'),
        ('done', 'Готово'),
    )

    PRIORITY_CHOICES = (
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
    )

    title = models.CharField('Заголовок задачи', max_length=200)
    description = models.TextField('Описание', blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name='Исполнитель',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tasks',
        verbose_name='Постановщик',
    )

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='client_tasks',
        verbose_name='Связанный клиент',
    )

    status = models.CharField('Статус (Канбан)', max_length=20, choices=KANBAN_STATUS, default='todo')
    priority = models.CharField('Приоритет', max_length=20, choices=PRIORITY_CHOICES, default='medium')
    is_pinned = models.BooleanField('Закреплена', default=False)
    deadline = models.DateTimeField('Дедлайн', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ('-is_pinned', '-updated_at')


class Project(models.Model):
    STATUS_CHOICES = (
        ('active', 'Активный'),
        ('paused', 'Пауза'),
        ('done', 'Завершён'),
        ('archived', 'Архив'),
    )

    title = models.CharField('Название проекта', max_length=255)
    description = models.TextField('Описание / Markdown', blank=True, default='')
    city = models.CharField('Город', max_length=100, blank=True, default='', db_index=True)
    office = models.ForeignKey(
        'users.Office',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='projects',
        verbose_name='Офис',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_projects',
        verbose_name='Создатель',
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='projects',
        verbose_name='Участники с доступом',
    )
    responsible_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='responsible_projects',
        verbose_name='Ответственные',
    )
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    deadline = models.DateTimeField('Дедлайн проекта', null=True, blank=True)
    is_hidden = models.BooleanField('Скрыт админом', default=False, db_index=True)
    is_pinned = models.BooleanField('Закреплён', default=False)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Проект'
        verbose_name_plural = 'Проекты'
        ordering = ['-is_pinned', '-updated_at']

    def __str__(self):
        return self.title


class ProjectSection(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='sections',
        verbose_name='Проект',
    )
    title = models.CharField('Название раздела', max_length=255)
    description = models.TextField('Описание раздела', blank=True, default='')
    color = models.CharField('Цвет', max_length=32, blank=True, default='')
    icon = models.CharField('Иконка', max_length=64, blank=True, default='')
    order = models.PositiveIntegerField('Порядок', default=0)
    is_pinned = models.BooleanField('Закреплён', default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_project_sections',
        verbose_name='Кто создал раздел',
    )
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Раздел проекта'
        verbose_name_plural = 'Разделы проектов'
        ordering = ['-is_pinned', 'order', '-updated_at']

    def __str__(self):
        return f'{self.project}: {self.title}'


class ProjectSectionPost(models.Model):
    section = models.ForeignKey(
        ProjectSection,
        on_delete=models.CASCADE,
        related_name='posts',
        verbose_name='Раздел',
    )
    title = models.CharField('Заголовок записи', max_length=255, blank=True, default='')
    body = models.TextField('Информация / текст поста', blank=True, default='')
    copy_text = models.TextField('Текст для копирования', blank=True, default='')
    note = models.TextField('Внутренняя заметка', blank=True, default='')
    is_pinned = models.BooleanField('Закреплена', default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_project_section_posts',
        verbose_name='Кто заполнил',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_project_section_posts',
        verbose_name='Кто обновил',
    )
    created_at = models.DateTimeField('Создана', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлена', auto_now=True)

    class Meta:
        verbose_name = 'Запись раздела проекта'
        verbose_name_plural = 'Записи разделов проектов'
        ordering = ['-is_pinned', '-updated_at']

    def __str__(self):
        return self.title or f'Запись #{self.id}'


class ProjectTask(models.Model):
    STATUS_CHOICES = (
        ('todo', 'Нужно сделать'),
        ('process', 'В работе'),
        ('review', 'На проверке'),
        ('done', 'Готово'),
    )

    PRIORITY_CHOICES = (
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий'),
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='items', verbose_name='Проект')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subtasks',
        verbose_name='Родительская задача',
    )
    title = models.CharField('Задача', max_length=255)
    description = models.TextField('Описание / Markdown', blank=True, default='')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_tasks',
        verbose_name='Ответственный',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_project_tasks',
        verbose_name='Кто создал',
    )
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='todo', db_index=True)
    priority = models.CharField('Приоритет', max_length=20, choices=PRIORITY_CHOICES, default='medium')
    deadline = models.DateTimeField('Дедлайн', null=True, blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Задача проекта'
        verbose_name_plural = 'Задачи проектов'
        ordering = ['parent_id', 'status', 'order', '-updated_at']

    def __str__(self):
        return self.title


class ProjectAttachment(models.Model):
    TYPE_CHOICES = (
        ('file', 'Файл'),
        ('image', 'Фото'),
        ('link', 'Ссылка'),
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='attachments', verbose_name='Проект')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_attachments',
        verbose_name='Кто добавил',
    )
    title = models.CharField('Название', max_length=255, blank=True, default='')
    attachment_type = models.CharField('Тип', max_length=20, choices=TYPE_CHOICES, default='file')
    file = models.FileField('Файл/Фото', upload_to='project_attachments/', null=True, blank=True)
    url = models.URLField('Ссылка', max_length=1000, blank=True, default='')
    note = models.TextField('Комментарий', blank=True, default='')
    created_at = models.DateTimeField('Добавлено', auto_now_add=True)

    class Meta:
        verbose_name = 'Файл/ссылка проекта'
        verbose_name_plural = 'Файлы и ссылки проектов'
        ordering = ['-created_at']

    def __str__(self):
        return self.title or self.url or f'Attachment #{self.id}'