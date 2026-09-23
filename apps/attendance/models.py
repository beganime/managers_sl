from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import ActiveModel, TimeStampedModel
from apps.organizations.models import Company, Office


class WorkDay(TimeStampedModel):
    STATUS_NOT_STARTED = 'not_started'
    STATUS_STARTED = 'started'
    STATUS_REPORT_SUBMITTED = 'report_submitted'
    STATUS_CLOSED = 'closed'
    STATUS_AUTO_CLOSED = 'auto_closed'
    STATUS_MISSED = 'missed'
    STATUS_CHOICES = (
        (STATUS_NOT_STARTED, 'Не начат'),
        (STATUS_STARTED, 'Рабочий день идёт'),
        (STATUS_REPORT_SUBMITTED, 'Отчёт отправлен'),
        (STATUS_CLOSED, 'Закрыт сотрудником'),
        (STATUS_AUTO_CLOSED, 'Закрыт автоматически'),
        (STATUS_MISSED, 'Не вышел на работу'),
    )
    FINAL_STATUSES = {STATUS_CLOSED, STATUS_AUTO_CLOSED, STATUS_MISSED}

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='attendance_workdays')
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='attendance_workdays',
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Employee', on_delete=models.PROTECT, related_name='attendance_workdays')
    date = models.DateField('Date', default=timezone.localdate, db_index=True)
    status = models.CharField('Status', max_length=32, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED, db_index=True)
    started_at = models.DateTimeField('Started at', null=True, blank=True)
    closed_at = models.DateTimeField('Closed at', null=True, blank=True)
    auto_closed_at = models.DateTimeField('Auto closed at', null=True, blank=True)
    total_work_seconds = models.PositiveIntegerField('Total work seconds', default=0)
    report_required = models.BooleanField('Report required', default=True)
    comment = models.TextField('Comment', blank=True)
    custom_data = models.JSONField('Custom data', default=dict, blank=True)

    class Meta:
        verbose_name = 'Work day'
        verbose_name_plural = 'Work days'
        ordering = ['-date', '-created_at']
        unique_together = [('company', 'employee', 'date')]
        indexes = [
            models.Index(fields=['company', 'office', 'status']),
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['date', 'status']),
        ]

    def __str__(self):
        return f'{self.employee} - {self.date}'

    @property
    def total_work_hours(self):
        return round(self.total_work_seconds / 3600, 2)

    @property
    def has_report(self):
        return hasattr(self, 'daily_report') and bool(self.daily_report.submitted_at)

    @property
    def requires_manual_close(self):
        return bool((self.custom_data or {}).get('requires_manual_close'))

    def recalculate_total(self, save=True):
        total = sum(session.duration_seconds for session in self.sessions.all())
        self.total_work_seconds = total
        if save:
            self.save(update_fields=['total_work_seconds', 'updated_at'])
        return total

    def start(self, note=''):
        if self.status in self.FINAL_STATUSES:
            raise ValueError('Завершённый рабочий день нельзя начать повторно.')

        now = timezone.now()
        notify_arrival = not self.started_at and self.status == self.STATUS_NOT_STARTED
        with transaction.atomic():
            active_session = self.sessions.filter(is_active=True).first()
            if not active_session:
                WorkSession.objects.create(
                    workday=self,
                    employee=self.employee,
                    started_at=now,
                    start_note=note or '',
                )

            if not self.started_at:
                self.started_at = now
            if self.status in {self.STATUS_NOT_STARTED, self.STATUS_MISSED}:
                self.status = self.STATUS_STARTED
            self.save(update_fields=['started_at', 'status', 'updated_at'])
        if notify_arrival:
            from .telegram import register_workday_event
            register_workday_event(self, AttendanceTelegramDelivery.EVENT_ARRIVAL)
        return self

    def submit_report(self, content, **extra):
        report, _ = DailyReport.objects.get_or_create(
            workday=self,
            defaults={
                'company': self.company,
                'office': self.office,
                'employee': self.employee,
                'date': self.date,
            },
        )
        report.content = content or report.content
        for field in ('results', 'plans', 'problems', 'leads_processed', 'deals_closed', 'comment'):
            if field in extra:
                setattr(report, field, extra[field])
        report.submitted_at = timezone.now()
        report.save()

        if self.status not in self.FINAL_STATUSES:
            self.status = self.STATUS_REPORT_SUBMITTED
            self.save(update_fields=['status', 'updated_at'])
        return report

    def close(self, user=None, comment='', auto=False):
        if self.status in {self.STATUS_CLOSED, self.STATUS_AUTO_CLOSED}:
            return self

        now = timezone.now()
        with transaction.atomic():
            previous_status = self.status
            for session in self.sessions.filter(is_active=True):
                session.close(ended_at=now, note=comment)

            self.recalculate_total(save=False)
            self.closed_at = now
            if comment:
                self.comment = comment
            custom_data = dict(self.custom_data or {})
            custom_data.pop('requires_manual_close', None)
            custom_data.pop('manual_close_reason', None)
            self.custom_data = custom_data
            if auto:
                self.status = self.STATUS_AUTO_CLOSED
                self.auto_closed_at = now
            else:
                self.status = self.STATUS_CLOSED
            self.save(update_fields=['status', 'closed_at', 'auto_closed_at', 'total_work_seconds', 'comment', 'custom_data', 'updated_at'])

            if auto:
                AutoCloseLog.objects.create(
                    workday=self,
                    company=self.company,
                    office=self.office,
                    employee=self.employee,
                    previous_status=previous_status,
                    reason=comment or 'Auto closed by scheduled job.',
                    success=True,
                )
        from .telegram import register_workday_event
        register_workday_event(
            self,
            AttendanceTelegramDelivery.EVENT_AUTO_CLOSE if auto else AttendanceTelegramDelivery.EVENT_DEPARTURE,
        )
        return self


class WorkSession(TimeStampedModel):
    workday = models.ForeignKey(WorkDay, verbose_name='Work day', on_delete=models.CASCADE, related_name='sessions')
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Employee', on_delete=models.PROTECT, related_name='attendance_sessions')
    started_at = models.DateTimeField('Started at', default=timezone.now, db_index=True)
    ended_at = models.DateTimeField('Ended at', null=True, blank=True)
    duration_seconds = models.PositiveIntegerField('Duration seconds', default=0)
    is_active = models.BooleanField('Active', default=True, db_index=True)
    start_note = models.TextField('Start note', blank=True)
    end_note = models.TextField('End note', blank=True)

    class Meta:
        verbose_name = 'Work session'
        verbose_name_plural = 'Work sessions'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['employee', 'is_active']),
            models.Index(fields=['workday', 'is_active']),
        ]

    def __str__(self):
        return f'{self.employee} - {self.started_at}'

    def calculate_duration(self, ended_at=None):
        end = ended_at or self.ended_at or timezone.now()
        if not self.started_at:
            return 0
        return max(0, int((end - self.started_at).total_seconds()))

    def close(self, ended_at=None, note=''):
        self.ended_at = ended_at or timezone.now()
        self.duration_seconds = self.calculate_duration(self.ended_at)
        self.is_active = False
        if note:
            self.end_note = note
        self.save(update_fields=['ended_at', 'duration_seconds', 'is_active', 'end_note', 'updated_at'])
        return self

    def save(self, *args, **kwargs):
        if self.ended_at:
            self.duration_seconds = self.calculate_duration(self.ended_at)
            self.is_active = False
        super().save(*args, **kwargs)


class DailyReport(TimeStampedModel):
    workday = models.OneToOneField(WorkDay, verbose_name='Work day', on_delete=models.CASCADE, related_name='daily_report')
    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='attendance_reports')
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='attendance_reports',
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Employee', on_delete=models.PROTECT, related_name='attendance_reports')
    date = models.DateField('Date', default=timezone.localdate, db_index=True)
    content = models.TextField('Content')
    results = models.TextField('Results', blank=True)
    plans = models.TextField('Plans', blank=True)
    problems = models.TextField('Problems', blank=True)
    leads_processed = models.PositiveIntegerField('Leads processed', default=0)
    deals_closed = models.PositiveIntegerField('Deals closed', default=0)
    comment = models.TextField('Comment', blank=True)
    submitted_at = models.DateTimeField('Submitted at', null=True, blank=True)

    class Meta:
        verbose_name = 'Daily report'
        verbose_name_plural = 'Daily reports'
        ordering = ['-date', '-submitted_at']
        unique_together = [('company', 'employee', 'date')]
        indexes = [
            models.Index(fields=['company', 'office', 'date']),
            models.Index(fields=['employee', 'date']),
        ]

    def __str__(self):
        return f'{self.employee} - {self.date}'

    def save(self, *args, **kwargs):
        if not self.submitted_at:
            self.submitted_at = timezone.now()
        super().save(*args, **kwargs)


class AttendanceReminder(TimeStampedModel, ActiveModel):
    REMINDER_START = 'start_workday'
    REMINDER_REPORT = 'daily_report'
    REMINDER_CLOSE = 'close_workday'
    REMINDER_CHOICES = (
        (REMINDER_START, 'Start workday'),
        (REMINDER_REPORT, 'Daily report'),
        (REMINDER_CLOSE, 'Close workday'),
    )

    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.CASCADE, related_name='attendance_reminders')
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.CASCADE,
        related_name='attendance_reminders',
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Employee',
        on_delete=models.CASCADE,
        related_name='attendance_reminders',
        null=True,
        blank=True,
    )
    reminder_type = models.CharField('Reminder type', max_length=32, choices=REMINDER_CHOICES, db_index=True)
    scheduled_time = models.TimeField('Scheduled time')
    weekdays = models.JSONField('Weekdays', default=list, blank=True)
    message = models.TextField('Message', blank=True)
    last_sent_at = models.DateTimeField('Last sent at', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Created by',
        on_delete=models.SET_NULL,
        related_name='created_attendance_reminders',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = 'Attendance reminder'
        verbose_name_plural = 'Attendance reminders'
        ordering = ['company__name', 'scheduled_time']
        indexes = [
            models.Index(fields=['company', 'office', 'reminder_type', 'is_active']),
        ]

    def __str__(self):
        return f'{self.get_reminder_type_display()} - {self.scheduled_time}'


class AutoCloseLog(TimeStampedModel):
    workday = models.ForeignKey(WorkDay, verbose_name='Work day', on_delete=models.CASCADE, related_name='auto_close_logs')
    company = models.ForeignKey(Company, verbose_name='Company', on_delete=models.PROTECT, related_name='attendance_auto_close_logs')
    office = models.ForeignKey(
        Office,
        verbose_name='Office',
        on_delete=models.SET_NULL,
        related_name='attendance_auto_close_logs',
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='Employee', on_delete=models.PROTECT, related_name='attendance_auto_close_logs')
    previous_status = models.CharField('Previous status', max_length=32, blank=True)
    reason = models.TextField('Reason', blank=True)
    success = models.BooleanField('Success', default=True)
    error_message = models.TextField('Error message', blank=True)

    class Meta:
        verbose_name = 'Auto close log'
        verbose_name_plural = 'Auto close logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'office', 'created_at']),
            models.Index(fields=['employee', 'created_at']),
        ]

    def __str__(self):
        return f'{self.employee} - {self.created_at}'


class AttendanceTelegramDelivery(TimeStampedModel):
    EVENT_ARRIVAL = 'arrival'
    EVENT_DEPARTURE = 'departure'
    EVENT_AUTO_CLOSE = 'auto_close'
    EVENT_MISSED = 'missed'
    EVENT_WEEKLY = 'weekly_summary'
    EVENT_START_REMINDER = 'start_reminder'
    EVENT_CLOSE_REMINDER = 'close_reminder'
    EVENT_AFTER_HOURS = 'after_hours'
    EVENT_CHOICES = (
        (EVENT_ARRIVAL, 'Приход'),
        (EVENT_DEPARTURE, 'Уход'),
        (EVENT_AUTO_CLOSE, 'Автоматическое закрытие'),
        (EVENT_MISSED, 'Неявка'),
        (EVENT_WEEKLY, 'Недельный отчёт'),
        (EVENT_START_REMINDER, 'Напоминание о начале дня'),
        (EVENT_CLOSE_REMINDER, 'Напоминание о завершении дня'),
        (EVENT_AFTER_HOURS, 'Активность после рабочего дня'),
    )

    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Ожидает'),
        (STATUS_SENT, 'Отправлено'),
        (STATUS_FAILED, 'Ошибка'),
    )

    event_key = models.CharField('Ключ события', max_length=190, unique=True)
    event_type = models.CharField('Тип события', max_length=32, choices=EVENT_CHOICES, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='attendance_telegram_deliveries')
    office = models.ForeignKey(
        Office,
        on_delete=models.SET_NULL,
        related_name='attendance_telegram_deliveries',
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='attendance_telegram_deliveries',
        null=True,
        blank=True,
    )
    workday = models.ForeignKey(
        WorkDay,
        on_delete=models.CASCADE,
        related_name='telegram_deliveries',
        null=True,
        blank=True,
    )
    message = models.TextField('Сообщение')
    target_chat_id = models.BigIntegerField('Получатель Telegram', null=True, blank=True)
    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField('Попытки', default=0)
    last_error = models.CharField('Последняя ошибка', max_length=255, blank=True)
    sent_at = models.DateTimeField('Отправлено', null=True, blank=True)

    class Meta:
        verbose_name = 'Telegram-событие рабочего дня'
        verbose_name_plural = 'Telegram-события рабочего дня'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['company', 'event_type', 'created_at']),
        ]

    def __str__(self):
        return f'{self.get_event_type_display()} — {self.event_key}'


class EmployeeTelegramAccount(TimeStampedModel, ActiveModel):
    employee = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attendance_telegram_account',
    )
    telegram_user_id = models.BigIntegerField('Telegram user ID', unique=True)
    chat_id = models.BigIntegerField('Telegram chat ID', unique=True)
    username = models.CharField('Telegram username', max_length=64, blank=True)
    first_name = models.CharField('Имя в Telegram', max_length=128, blank=True)
    last_name = models.CharField('Фамилия в Telegram', max_length=128, blank=True)
    linked_at = models.DateTimeField('Подключён', default=timezone.now)

    class Meta:
        verbose_name = 'Telegram сотрудника'
        verbose_name_plural = 'Telegram сотрудников'

    def __str__(self):
        return f'{self.employee} — @{self.username}' if self.username else str(self.employee)


class TelegramLinkCode(TimeStampedModel):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attendance_telegram_link_codes',
    )
    code_hash = models.CharField('Хеш кода', max_length=64, unique=True)
    expires_at = models.DateTimeField('Действует до', db_index=True)
    used_at = models.DateTimeField('Использован', null=True, blank=True)

    class Meta:
        verbose_name = 'Код подключения Telegram'
        verbose_name_plural = 'Коды подключения Telegram'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee} — {self.expires_at}'
