import logging
from datetime import timedelta

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.employees.models import EmployeeProfile
from apps.organizations.models import Company

from .models import AttendanceTelegramDelivery, WorkDay

logger = logging.getLogger(__name__)


def employee_name(user):
    return (user.get_full_name() or user.email).strip()


def office_name(workday):
    return str(workday.office) if workday.office_id else 'Без офиса'


def local_time(value):
    return timezone.localtime(value).strftime('%H:%M') if value else '—'


def workday_message(workday, event_type):
    name = employee_name(workday.employee)
    office = office_name(workday)
    date_text = workday.date.strftime('%d.%m.%Y')
    if event_type == AttendanceTelegramDelivery.EVENT_ARRIVAL:
        return f'#приход\n{name}\nОфис: {office}\nДата: {date_text}\nНачало: {local_time(workday.started_at)}'
    if event_type == AttendanceTelegramDelivery.EVENT_DEPARTURE:
        return f'#уход\n{name}\nОфис: {office}\nДата: {date_text}\nЗавершение: {local_time(workday.closed_at)}'
    if event_type == AttendanceTelegramDelivery.EVENT_AUTO_CLOSE:
        return (
            f'#автозакрытие\n{name}\nОфис: {office}\nДата: {date_text}\n'
            f'День закрыт системой: {local_time(workday.closed_at)}'
        )
    if event_type == AttendanceTelegramDelivery.EVENT_MISSED:
        return f'#неявка\n{name}\nОфис: {office}\nДата: {date_text}\nРабочий день не был начат.'
    raise ValueError(f'Unsupported attendance Telegram event: {event_type}')


def _enqueue(delivery):
    transaction.on_commit(lambda: _safe_delay(delivery.pk))


def _safe_delay(delivery_id):
    try:
        send_attendance_telegram_delivery.delay(delivery_id)
    except Exception:
        logger.warning('Could not enqueue attendance Telegram delivery %s.', delivery_id)


def register_workday_event(workday, event_type):
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return None
    event_key = f'workday:{workday.pk}:{event_type}'
    delivery, created = AttendanceTelegramDelivery.objects.get_or_create(
        event_key=event_key,
        defaults={
            'event_type': event_type,
            'company': workday.company,
            'office': workday.office,
            'employee': workday.employee,
            'workday': workday,
            'message': workday_message(workday, event_type),
        },
    )
    if created:
        _enqueue(delivery)
    return delivery


def send_telegram_message(message):
    token = settings.ATTENDANCE_TELEGRAM_BOT_TOKEN
    chat_id = settings.ATTENDANCE_TELEGRAM_CHAT_ID
    if not settings.ATTENDANCE_TELEGRAM_ENABLED or not token or not chat_id:
        return False, 'Telegram attendance is not configured.'
    base = settings.ATTENDANCE_TELEGRAM_API_BASE.rstrip('/')
    try:
        response = requests.post(
            f'{base}/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': message, 'disable_web_page_preview': True},
            timeout=20,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return False, type(exc).__name__
    if response.status_code == 200 and data.get('ok') is True:
        return True, ''
    return False, f'HTTP {response.status_code}'


@shared_task(name='attendance.send_telegram_delivery')
def send_attendance_telegram_delivery(delivery_id):
    with transaction.atomic():
        delivery = AttendanceTelegramDelivery.objects.select_for_update().filter(pk=delivery_id).first()
        if not delivery or delivery.status == AttendanceTelegramDelivery.STATUS_SENT:
            return {'sent': bool(delivery), 'reason': 'already_sent_or_missing'}
        delivery.attempts += 1
        sent, error = send_telegram_message(delivery.message)
        delivery.status = AttendanceTelegramDelivery.STATUS_SENT if sent else AttendanceTelegramDelivery.STATUS_FAILED
        delivery.last_error = error[:255]
        delivery.sent_at = timezone.now() if sent else None
        delivery.save(update_fields=['attempts', 'status', 'last_error', 'sent_at', 'updated_at'])
    return {'sent': sent}


@shared_task(name='attendance.retry_telegram_deliveries')
def retry_attendance_telegram_deliveries(limit=50):
    ids = list(
        AttendanceTelegramDelivery.objects.filter(
            status__in=[AttendanceTelegramDelivery.STATUS_PENDING, AttendanceTelegramDelivery.STATUS_FAILED],
            attempts__lt=5,
        ).order_by('created_at').values_list('pk', flat=True)[:limit]
    )
    for delivery_id in ids:
        _safe_delay(delivery_id)
    return {'queued': len(ids)}


def _summary_period(today):
    # The company works Monday-Saturday. On Sunday report the week ending yesterday.
    period_end = today - timedelta(days=1) if today.weekday() == 6 else today
    period_start = period_end - timedelta(days=period_end.weekday())
    return period_start, period_end


def weekly_summary_messages(company, period_start, period_end):
    weekdays = set(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5)))
    dates = [
        period_start + timedelta(days=offset)
        for offset in range((period_end - period_start).days + 1)
        if (period_start + timedelta(days=offset)).weekday() in weekdays
    ]
    profiles = EmployeeProfile.objects.select_related('user', 'office', 'access').filter(
        company=company,
        is_active=True,
        work_status='working',
        user__is_active=True,
        hire_date__lte=period_end,
    ).filter(Q(access__must_track_workday=True) | Q(access__isnull=True)).order_by(
        'office__city', 'office__name', 'user__first_name', 'user__last_name', 'user__email'
    )
    workdays = {
        (row.employee_id, row.date): row
        for row in WorkDay.objects.filter(company=company, date__range=(period_start, period_end))
    }
    grouped = {}
    for profile in profiles:
        grouped.setdefault(str(profile.office) if profile.office_id else 'Без офиса', []).append(profile)

    header = f'#недельный_отчёт\n{company.name}\n{period_start:%d.%m.%Y}–{period_end:%d.%m.%Y}'
    lines = [header]
    attended_statuses = {
        WorkDay.STATUS_STARTED,
        WorkDay.STATUS_REPORT_SUBMITTED,
        WorkDay.STATUS_CLOSED,
        WorkDay.STATUS_AUTO_CLOSED,
    }
    for office, office_profiles in grouped.items():
        lines.append(f'\nОфис: {office}')
        for profile in office_profiles:
            employee_dates = [day for day in dates if day >= profile.hire_date]
            markers = []
            attended = 0
            for day in employee_dates:
                row = workdays.get((profile.user_id, day))
                present = bool(row and row.status in attended_statuses)
                attended += int(present)
                markers.append(f'{day:%d.%m} {"✅" if present else "❌"}')
            lines.append(
                f'{employee_name(profile.user)}: {", ".join(markers) or "нет рабочих дней"} '
                f'({attended}/{len(employee_dates)})'
            )
    if len(lines) == 1:
        lines.append('Нет сотрудников для учёта.')

    messages = []
    current = ''
    continuation = f'{header}\nПродолжение'
    for line in lines:
        candidate = f'{current}\n{line}' if current else line
        if len(candidate) > 3800 and current:
            messages.append(current)
            current = f'{continuation}\n{line}'
        else:
            current = candidate
    messages.append(current)
    return messages


@shared_task(name='attendance.send_weekly_summary')
def send_weekly_attendance_summary():
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return {'created': 0, 'reason': 'disabled'}
    today = timezone.localdate()
    period_start, period_end = _summary_period(today)
    created = 0
    for company in Company.objects.filter(is_active=True):
        for index, message in enumerate(weekly_summary_messages(company, period_start, period_end), 1):
            delivery, was_created = AttendanceTelegramDelivery.objects.get_or_create(
                event_key=f'weekly:{company.pk}:{period_start}:{period_end}:{index}',
                defaults={
                    'event_type': AttendanceTelegramDelivery.EVENT_WEEKLY,
                    'company': company,
                    'message': message,
                },
            )
            if was_created:
                created += 1
                _enqueue(delivery)
    return {'created': created, 'period_start': str(period_start), 'period_end': str(period_end)}
