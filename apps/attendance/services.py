from datetime import datetime, time

from django.conf import settings
from django.utils import timezone

from apps.core.permissions import get_employee_profile, is_attendance_admin

from .models import AttendanceTelegramDelivery, AutoCloseLog, WorkDay


def is_scheduled_workday(day):
    return day.weekday() in set(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5)))


def should_track_employee(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if is_attendance_admin(user):
        return False
    employee = get_employee_profile(user)
    return bool(employee and employee.is_active)


def workday_close_at(day=None):
    day = day or timezone.localdate()
    close_time = time(
        getattr(settings, 'ATTENDANCE_AUTO_CLOSE_HOUR', 18),
        getattr(settings, 'ATTENDANCE_AUTO_CLOSE_MINUTE', 0),
    )
    return timezone.make_aware(datetime.combine(day, close_time), timezone.get_current_timezone())


def is_after_workday_close(value=None):
    value = value or timezone.now()
    local_value = timezone.localtime(value)
    return local_value >= workday_close_at(local_value.date())


def record_after_hours_activity(user, value=None):
    """Record portal activity after 18:00 without reopening a finished workday."""
    value = value or timezone.now()
    today = timezone.localdate(value)
    if not is_scheduled_workday(today) or not should_track_employee(user) or not is_after_workday_close(value):
        return None, False

    employee = get_employee_profile(user)
    workday, _ = WorkDay.objects.get_or_create(
        company=employee.company,
        employee=user,
        date=today,
        defaults={
            'office': employee.office,
            'status': WorkDay.STATUS_MISSED,
            'closed_at': workday_close_at(today),
            'comment': 'Рабочий день не был начат до 18:00.',
            'report_required': True,
        },
    )
    if workday.status == WorkDay.STATUS_NOT_STARTED:
        previous_status = workday.status
        workday.status = WorkDay.STATUS_MISSED
        workday.closed_at = workday_close_at(today)
        workday.comment = workday.comment or 'Рабочий день не был начат до 18:00.'
        AutoCloseLog.objects.create(
            workday=workday,
            company=workday.company,
            office=workday.office,
            employee=workday.employee,
            previous_status=previous_status,
            reason='Рабочий день не был начат до 18:00.',
            success=True,
        )

    custom_data = dict(workday.custom_data or {})
    first_seen = custom_data.get('after_hours_first_seen_at')
    last_seen = custom_data.get('after_hours_last_seen_at')
    try:
        if last_seen and (value - datetime.fromisoformat(last_seen)).total_seconds() < 50:
            return workday, False
    except (TypeError, ValueError):
        pass
    custom_data['after_hours_first_seen_at'] = first_seen or value.isoformat()
    custom_data['after_hours_last_seen_at'] = value.isoformat()
    custom_data['after_hours_activity_count'] = int(custom_data.get('after_hours_activity_count') or 0) + 1
    workday.custom_data = custom_data
    update_fields = ['custom_data', 'updated_at']
    if workday.status == WorkDay.STATUS_MISSED:
        update_fields.extend(['status', 'closed_at', 'comment'])
    workday.save(update_fields=update_fields)

    created = not bool(first_seen)
    if created:
        from .telegram import register_workday_event
        register_workday_event(workday, AttendanceTelegramDelivery.EVENT_AFTER_HOURS)
    return workday, created


def auto_start_workday_for_login(user):
    """Start today's attendance once on the first authenticated portal visit."""
    today = timezone.localdate()
    if not is_scheduled_workday(today) or not should_track_employee(user):
        return None, False

    if is_after_workday_close():
        workday, _ = record_after_hours_activity(user)
        return workday, False

    employee = get_employee_profile(user)
    workday, _ = WorkDay.objects.get_or_create(
        company=employee.company,
        employee=user,
        date=today,
        defaults={
            'office': employee.office,
            'status': WorkDay.STATUS_NOT_STARTED,
            'report_required': True,
        },
    )
    if employee.office_id and workday.office_id != employee.office_id:
        workday.office = employee.office
        workday.save(update_fields=['office', 'updated_at'])
    if workday.status == WorkDay.STATUS_NOT_STARTED:
        workday.start(note='Автоматически при входе в ManagerSL.')
        return workday, True
    return workday, False
