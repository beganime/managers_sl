from django.conf import settings
from django.utils import timezone

from apps.core.permissions import get_employee_profile

from .models import WorkDay


def is_scheduled_workday(day):
    return day.weekday() in set(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5)))


def should_track_employee(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    employee = get_employee_profile(user)
    if not employee or not employee.is_active or employee.work_status != 'working':
        return False
    access = getattr(employee, 'access', None)
    return bool(not access or access.must_track_workday)


def auto_start_workday_for_login(user):
    """Start today's attendance once on the first authenticated portal visit."""
    today = timezone.localdate()
    if not is_scheduled_workday(today) or not should_track_employee(user):
        return None, False

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
