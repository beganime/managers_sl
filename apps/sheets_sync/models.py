from django.db import models

from apps.core.models import TimeStampedModel


class SheetRowBinding(TimeStampedModel):
    ENTITY_CLIENT = 'client'
    ENTITY_APPLICATION = 'application'
    ENTITY_FINANCE = 'finance'
    ENTITY_EXAM = 'exam'
    ENTITY_CHOICES = (
        (ENTITY_CLIENT, 'Клиент'),
        (ENTITY_APPLICATION, 'Заявка в ВУЗ'),
        (ENTITY_FINANCE, 'Финансовая операция'),
        (ENTITY_EXAM, 'Экзамен'),
    )

    spreadsheet_id = models.CharField('ID книги', max_length=160, db_index=True)
    sheet_name = models.CharField('Лист', max_length=100)
    entity_type = models.CharField('Тип сущности', max_length=32, choices=ENTITY_CHOICES)
    object_ref = models.CharField('ID объекта ManagerSL', max_length=100)
    sl_id = models.CharField('SL-ID', max_length=32, db_index=True)
    row_number = models.PositiveIntegerField('Номер строки')
    sync_version = models.PositiveIntegerField('Версия синхронизации', default=1)
    row_hash = models.CharField('Хеш синхронизированных данных', max_length=64, blank=True)
    last_synced_at = models.DateTimeField('Последняя синхронизация', null=True, blank=True)

    class Meta:
        verbose_name = 'Связь со строкой Google Sheets'
        verbose_name_plural = 'Связи со строками Google Sheets'
        ordering = ['sheet_name', 'row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['spreadsheet_id', 'sheet_name', 'sl_id'],
                name='uniq_sheet_row_by_sl_id',
            ),
            models.UniqueConstraint(
                fields=['spreadsheet_id', 'sheet_name', 'entity_type', 'object_ref'],
                name='uniq_sheet_row_by_object',
            ),
        ]
        indexes = [
            models.Index(
                fields=['entity_type', 'object_ref'],
                name='sheets_sync_entity__9d1d17_idx',
            ),
            models.Index(
                fields=['spreadsheet_id', 'sheet_name', 'row_number'],
                name='sheets_sync_spreads_7f32c9_idx',
            ),
        ]

    def __str__(self):
        return f'{self.sheet_name}!{self.row_number} — {self.sl_id}'


class SheetSyncRun(TimeStampedModel):
    KIND_REFERENCES = 'references'
    KIND_SUBMISSION = 'submission'
    KIND_PENDING = 'pending'
    KIND_PUBLIC_STATUS = 'public_status'
    KIND_ONBOARDING_INBOX = 'onboarding_inbox'
    KIND_ONBOARDING_DECISIONS = 'onboarding_decisions'
    KIND_CHOICES = (
        (KIND_REFERENCES, 'Справочники'),
        (KIND_SUBMISSION, 'Анкета'),
        (KIND_PENDING, 'Очередь анкет'),
        (KIND_PUBLIC_STATUS, 'Статусы клиентов'),
        (KIND_ONBOARDING_INBOX, 'Входящие анкеты'),
        (KIND_ONBOARDING_DECISIONS, 'Решения по анкетам'),
    )

    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = (
        (STATUS_RUNNING, 'Выполняется'),
        (STATUS_SUCCESS, 'Успешно'),
        (STATUS_FAILED, 'Ошибка'),
        (STATUS_SKIPPED, 'Пропущено'),
    )

    kind = models.CharField('Тип запуска', max_length=24, choices=KIND_CHOICES)
    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    object_ref = models.CharField('Связанный объект', max_length=100, blank=True)
    processed = models.PositiveIntegerField('Обработано', default=0)
    failed = models.PositiveIntegerField('Ошибок', default=0)
    error = models.TextField('Ошибка', blank=True)
    finished_at = models.DateTimeField('Завершено', null=True, blank=True)

    class Meta:
        verbose_name = 'Запуск синхронизации Google Sheets'
        verbose_name_plural = 'Запуски синхронизации Google Sheets'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['kind', 'status', 'created_at'],
                name='sheets_sync_kind_eb6dc5_idx',
            )
        ]

    def __str__(self):
        return f'{self.get_kind_display()} — {self.get_status_display()}'


class ClientAdmissionSnapshot(TimeStampedModel):
    """Only the Google Sheets fields that are safe to show to a client."""

    client = models.OneToOneField(
        'crm.Client',
        verbose_name='Клиент',
        on_delete=models.CASCADE,
        related_name='admission_snapshot',
    )
    current_status = models.CharField('Текущий статус', max_length=255, blank=True)
    invitation_city = models.CharField('Город приглашения', max_length=255, blank=True)
    meeting = models.CharField('Встреча', max_length=100, blank=True)
    current_location = models.CharField('Текущее местонахождение', max_length=255, blank=True)
    spreadsheet_id = models.CharField('ID книги', max_length=160)
    sheet_name = models.CharField('Лист', max_length=100)
    row_number = models.PositiveIntegerField('Номер строки')
    source_hash = models.CharField('Хеш исходных данных', max_length=64)
    source_updated_value = models.CharField('Значение «Обновлено»', max_length=100, blank=True)
    last_imported_at = models.DateTimeField('Последний импорт')

    class Meta:
        verbose_name = 'Публичный статус поступления'
        verbose_name_plural = 'Публичные статусы поступления'
        ordering = ['client__sl_id']

    def __str__(self):
        return f'{self.client.sl_id}: {self.current_status or "без статуса"}'


class SheetSearchSource(TimeStampedModel):
    title = models.CharField('Название книги', max_length=160)
    spreadsheet_id = models.CharField('ID Google Sheets', max_length=160, unique=True)
    is_active = models.BooleanField('Искать в этой книге', default=True, db_index=True)

    class Meta:
        verbose_name = 'Источник поиска Google Sheets'
        verbose_name_plural = 'Источники поиска Google Sheets'
        ordering = ['title']

    def __str__(self):
        return self.title
