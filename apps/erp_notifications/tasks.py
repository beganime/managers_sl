from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

try:
    from celery import shared_task
except ImportError:
    def shared_task(*decorator_args, **decorator_kwargs):
        def decorator(func):
            return func
        return decorator

from apps.attendance.models import AttendanceReminder, AttendanceTelegramDelivery, AutoCloseLog, WorkDay
from apps.attendance.telegram import register_personal_reminder, register_workday_event
from apps.employees.models import EmployeeProfile
from apps.erp_documents.models import DocumentApproval
from apps.finance.models import Payment
from apps.projects_v2.models import ProjectTask

from .models import Notification, NotificationTemplate
from .services import create_notification, get_admin_users, send_birthday_reminders_for_date, send_notification


def notification_exists(related_object, notification_type, recipient=None, since=None):
    content_type = ContentType.objects.get_for_model(related_object, for_concrete_model=False)
    qs = Notification.objects.filter(
        content_type=content_type,
        object_id=related_object.pk,
        notification_type=notification_type,
    )
    if recipient:
        qs = qs.filter(recipient=recipient)
    if since:
        qs = qs.filter(created_at__gte=since)
    return qs.exists()


def reminder_already_sent(reminder, recipient, reminder_type, today):
    return Notification.objects.filter(
        recipient=recipient,
        notification_type=NotificationTemplate.TYPE_ATTENDANCE,
        data__reminder_id=reminder.id,
        data__reminder_type=reminder_type,
        created_at__date=today,
    ).exists()


def reminder_due(reminder, now):
    today = timezone.localdate()
    weekdays = reminder.weekdays or []
    if weekdays and now.weekday() not in [int(day) for day in weekdays]:
        return False
    if reminder.last_sent_at and timezone.localtime(reminder.last_sent_at).date() == today:
        return False
    scheduled_at = timezone.make_aware(datetime.combine(today, reminder.scheduled_time), timezone.get_current_timezone())
    return scheduled_at <= now <= scheduled_at + timedelta(minutes=15)


def reminder_recipients(reminder):
    if reminder.employee_id:
        return [reminder.employee]

    employees = EmployeeProfile.objects.filter(
        company=reminder.company,
        is_active=True,
        work_status='working',
        user__is_active=True,
    ).filter(Q(access__must_track_workday=True) | Q(access__isnull=True)).select_related('user')
    if reminder.office_id:
        employees = employees.filter(Q(office=reminder.office) | Q(office__isnull=True))
    return [employee.user for employee in employees]


def attendance_workday_is_scheduled(today):
    return today.weekday() in set(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5)))


def ensure_default_attendance_reminders():
    """Create company-wide defaults while preserving any configured reminder of the same type."""
    from apps.organizations.models import Company

    definitions = (
        (
            AttendanceReminder.REMINDER_START,
            getattr(settings, 'ATTENDANCE_WORKDAY_START_HOUR', 9),
            getattr(settings, 'ATTENDANCE_WORKDAY_START_MINUTE', 0),
            'Рабочий день начинается в 09:00. Отметьте начало дня в ManagerSL.',
        ),
        (
            AttendanceReminder.REMINDER_REPORT,
            getattr(settings, 'ATTENDANCE_REPORT_REMINDER_HOUR', 17),
            getattr(settings, 'ATTENDANCE_REPORT_REMINDER_MINUTE', 40),
            'Подведите итоги дня: заполните короткий отчёт перед завершением работы.',
        ),
        (
            AttendanceReminder.REMINDER_CLOSE,
            getattr(settings, 'ATTENDANCE_CLOSE_REMINDER_HOUR', 17),
            getattr(settings, 'ATTENDANCE_CLOSE_REMINDER_MINUTE', 55),
            'Рабочий день заканчивается в 18:00. Проверьте отчёт и закройте день.',
        ),
    )
    weekdays = list(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5)))
    for company in Company.objects.filter(is_active=True):
        for reminder_type, hour, minute, message in definitions:
            if AttendanceReminder.objects.filter(
                company=company,
                reminder_type=reminder_type,
                is_active=True,
            ).exists():
                continue
            AttendanceReminder.objects.create(
                company=company,
                reminder_type=reminder_type,
                scheduled_time=datetime.min.replace(hour=hour, minute=minute).time(),
                weekdays=weekdays,
                message=message,
            )


def should_send_attendance_reminder(user, reminder_type, today):
    workday = WorkDay.objects.filter(employee=user, date=today).first()
    if reminder_type == AttendanceReminder.REMINDER_START:
        return not workday or workday.status in {WorkDay.STATUS_NOT_STARTED, WorkDay.STATUS_MISSED}
    if reminder_type == AttendanceReminder.REMINDER_REPORT:
        return bool(workday and workday.status == WorkDay.STATUS_STARTED and not workday.has_report)
    if reminder_type == AttendanceReminder.REMINDER_CLOSE:
        return bool(workday and workday.status in {WorkDay.STATUS_STARTED, WorkDay.STATUS_REPORT_SUBMITTED})
    return False


@shared_task(name='erp_notifications.send_notification')
def send_notification_task(notification_id):
    notification = Notification.objects.select_related('recipient').filter(pk=notification_id).first()
    if not notification:
        return {'sent': False, 'reason': 'not_found'}
    return {'sent': send_notification(notification)}


@shared_task(name='erp_notifications.send_queued_notifications')
def send_queued_notifications(limit=100):
    notifications = Notification.objects.select_related('recipient').filter(
        status__in=[Notification.STATUS_NEW, Notification.STATUS_QUEUED],
    ).order_by('created_at')[:limit]
    sent = 0
    failed = 0
    for notification in notifications:
        if send_notification(notification):
            sent += 1
        else:
            failed += 1
    return {'sent': sent, 'failed': failed}


@shared_task(name='erp_notifications.auto_close_workdays')
def auto_close_workdays():
    today = timezone.localdate()
    now = timezone.now()
    if attendance_workday_is_scheduled(today):
        profiles = EmployeeProfile.objects.select_related('user', 'company', 'office', 'access').filter(
            is_active=True,
            work_status='working',
            user__is_active=True,
        ).filter(Q(access__must_track_workday=True) | Q(access__isnull=True))
        for profile in profiles.iterator():
            WorkDay.objects.get_or_create(
                company=profile.company,
                employee=profile.user,
                date=today,
                defaults={
                    'office': profile.office,
                    'status': WorkDay.STATUS_NOT_STARTED,
                    'report_required': True,
                },
            )
    qs = WorkDay.objects.select_related('company', 'office', 'employee').filter(
        date__lte=today,
        status__in=[WorkDay.STATUS_NOT_STARTED, WorkDay.STATUS_STARTED, WorkDay.STATUS_REPORT_SUBMITTED],
    ).filter(Q(employee__employee_profile__access__must_track_workday=True) | Q(employee__employee_profile__access__isnull=True))
    closed = 0
    missed = 0
    waiting_manual_close = 0
    failed = 0
    for workday in qs.iterator():
        try:
            if workday.status == WorkDay.STATUS_NOT_STARTED:
                previous_status = workday.status
                workday.status = WorkDay.STATUS_MISSED
                workday.closed_at = now
                workday.comment = workday.comment or 'Рабочий день не был начат до 18:00.'
                workday.save(update_fields=['status', 'closed_at', 'comment', 'updated_at'])
                AutoCloseLog.objects.create(
                    workday=workday,
                    company=workday.company,
                    office=workday.office,
                    employee=workday.employee,
                    previous_status=previous_status,
                    reason='Рабочий день не был начат до 18:00.',
                    success=True,
                )
                register_workday_event(workday, AttendanceTelegramDelivery.EVENT_MISSED)
                missed += 1
            else:
                workday.close(auto=True, comment='Автоматически закрыт системой в 18:00.')
                closed += 1

            create_notification(
                workday.employee,
                title='Рабочий день завершён' if workday.status != WorkDay.STATUS_MISSED else 'Рабочий день не был начат',
                body=(
                    'Система закрыла рабочий день автоматически в 18:00.'
                    if workday.status != WorkDay.STATUS_MISSED
                    else 'Начало рабочего дня сегодня не отмечено. В учёте день записан как отсутствие.'
                ),
                notification_type=NotificationTemplate.TYPE_ATTENDANCE,
                channel=NotificationTemplate.CHANNEL_PUSH,
                priority=Notification.PRIORITY_NORMAL,
                data={'workday_id': workday.id, 'status': workday.status},
                related_object=workday,
                company=workday.company,
                office=workday.office,
            )
        except Exception as exc:
            failed += 1
            AutoCloseLog.objects.create(
                workday=workday,
                company=workday.company,
                office=workday.office,
                employee=workday.employee,
                previous_status=workday.status,
                reason='Auto close failed.',
                success=False,
                error_message=str(exc),
            )
    return {'closed': closed, 'missed': missed, 'waiting_manual_close': waiting_manual_close, 'failed': failed}


def send_attendance_reminders(reminder_type):
    ensure_default_attendance_reminders()
    now = timezone.localtime()
    today = timezone.localdate()
    reminders = AttendanceReminder.objects.select_related('company', 'office', 'employee').filter(
        reminder_type=reminder_type,
        is_active=True,
    )
    created = 0
    for reminder in reminders:
        if not reminder_due(reminder, now):
            continue
        for recipient in reminder_recipients(reminder):
            if reminder_already_sent(reminder, recipient, reminder_type, today):
                continue
            if not should_send_attendance_reminder(recipient, reminder_type, today):
                continue
            reminder_titles = {
                AttendanceReminder.REMINDER_START: 'Начните рабочий день',
                AttendanceReminder.REMINDER_REPORT: 'Подведите итоги дня',
                AttendanceReminder.REMINDER_CLOSE: 'Завершите рабочий день',
            }
            create_notification(
                recipient,
                title=reminder_titles.get(reminder_type, 'Рабочий день'),
                body=reminder.message or reminder.get_reminder_type_display(),
                notification_type=NotificationTemplate.TYPE_ATTENDANCE,
                channel=NotificationTemplate.CHANNEL_PUSH,
                priority=Notification.PRIORITY_NORMAL,
                data={
                    'reminder_id': reminder.id,
                    'reminder_type': reminder_type,
                    'date': str(today),
                    'screen': 'workday',
                },
                company=reminder.company,
                office=reminder.office,
            )
            register_personal_reminder(recipient, reminder_type, today)
            created += 1
        reminder.last_sent_at = timezone.now()
        reminder.save(update_fields=['last_sent_at', 'updated_at'])
    return created


@shared_task(name='erp_notifications.daily_start_reminder')
def daily_start_reminder():
    return {'created': send_attendance_reminders(AttendanceReminder.REMINDER_START)}


@shared_task(name='erp_notifications.daily_report_reminder')
def daily_report_reminder():
    return {'created': send_attendance_reminders(AttendanceReminder.REMINDER_REPORT)}


@shared_task(name='erp_notifications.close_workday_reminder')
def close_workday_reminder():
    return {'created': send_attendance_reminders(AttendanceReminder.REMINDER_CLOSE)}


@shared_task(name='erp_notifications.task_reminders')
def task_reminders(hours_ahead=24):
    now = timezone.now()
    deadline_to = now + timedelta(hours=hours_ahead)
    tasks = ProjectTask.objects.select_related('project', 'project__company', 'project__office', 'assigned_to').filter(
        assigned_to__isnull=False,
        deadline__isnull=False,
        deadline__gte=now,
        deadline__lte=deadline_to,
    ).exclude(status__in=[ProjectTask.STATUS_DONE, ProjectTask.STATUS_CANCELLED])

    created = 0
    since = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    for task in tasks:
        if notification_exists(task, NotificationTemplate.TYPE_TASK, recipient=task.assigned_to, since=since):
            continue
        create_notification(
            task.assigned_to,
            title='Task deadline is close',
            body=f'{task.title} is due at {timezone.localtime(task.deadline).strftime("%Y-%m-%d %H:%M")}.',
            notification_type=NotificationTemplate.TYPE_TASK,
            priority=Notification.PRIORITY_HIGH,
            data={'task_id': task.id, 'project_id': task.project_id, 'screen': 'projects'},
            target_url=f'/portal/projects/tasks/{task.id}/',
            related_object=task,
            company=task.project.company,
            office=task.project.office,
        )
        created += 1
    return {'created': created}


@shared_task(name='erp_notifications.document_approval_notification')
def document_approval_notification():
    approvals = DocumentApproval.objects.select_related(
        'document',
        'document__company',
        'document__office',
        'document__manager',
    ).filter(status=DocumentApproval.STATUS_PENDING)
    created = 0
    for approval in approvals:
        document = approval.document
        recipients = get_admin_users(company=document.company, office=document.office)
        for recipient in recipients:
            if notification_exists(document, NotificationTemplate.TYPE_DOCUMENT, recipient=recipient):
                continue
            notification = create_notification(
                recipient,
                title='Document waiting for approval',
                body=f'{document.title or document.template.name} is waiting for approval.',
                notification_type=NotificationTemplate.TYPE_DOCUMENT,
                priority=Notification.PRIORITY_HIGH,
                data={'document_id': document.id, 'approval_id': approval.id, 'screen': 'documents'},
                target_url=f'/portal/documents/{document.id}/',
                related_object=document,
                company=document.company,
                office=document.office,
            )
            if notification:
                created += 1
    return {'created': created}


@shared_task(name='erp_notifications.payment_confirmation_notification')
def payment_confirmation_notification():
    payments = Payment.objects.select_related('company', 'office', 'client', 'deal', 'manager', 'confirmed_by').filter(is_confirmed=True)
    created = 0
    for payment in payments:
        recipients = {payment.manager}
        recipients.update(get_admin_users(company=payment.company, office=payment.office))
        for recipient in recipients:
            if not recipient or notification_exists(payment, NotificationTemplate.TYPE_PAYMENT, recipient=recipient):
                continue
            notification = create_notification(
                recipient,
                title='Payment confirmed',
                body=f'Payment for {payment.client} was confirmed: {payment.amount_usd} USD.',
                notification_type=NotificationTemplate.TYPE_PAYMENT,
                priority=Notification.PRIORITY_HIGH,
                data={'payment_id': payment.id, 'deal_id': payment.deal_id, 'screen': 'finance'},
                target_url=f'/portal/finance/payments/{payment.id}/',
                related_object=payment,
                company=payment.company,
                office=payment.office,
            )
            if notification:
                created += 1
    return {'created': created}


@shared_task(name='erp_notifications.send_birthday_reminders')
def send_birthday_reminders_task():
    return send_birthday_reminders_for_date()
