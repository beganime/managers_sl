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
        (STATUS_NOT_STARTED, 'Not started'),
        (STATUS_STARTED, 'Started'),
        (STATUS_REPORT_SUBMITTED, 'Report submitted'),
        (STATUS_CLOSED, 'Closed'),
        (STATUS_AUTO_CLOSED, 'Auto closed'),
        (STATUS_MISSED, 'Missed'),
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

    def recalculate_total(self, save=True):
        total = sum(session.duration_seconds for session in self.sessions.all())
        self.total_work_seconds = total
        if save:
            self.save(update_fields=['total_work_seconds', 'updated_at'])
        return total

    def start(self, note=''):
        if self.status in {self.STATUS_CLOSED, self.STATUS_AUTO_CLOSED}:
            raise ValueError('Closed workday cannot be started again.')

        now = timezone.now()
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
            if auto:
                self.status = self.STATUS_AUTO_CLOSED
                self.auto_closed_at = now
            else:
                self.status = self.STATUS_CLOSED
            self.save(update_fields=['status', 'closed_at', 'auto_closed_at', 'total_work_seconds', 'comment', 'updated_at'])

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
