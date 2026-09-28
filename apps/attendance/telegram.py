import logging
import hashlib
import secrets
from uuid import uuid4
from datetime import datetime, timedelta, timezone as datetime_timezone

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.employees.models import EmployeeProfile
from apps.organizations.models import Company

from .models import AttendanceTelegramDelivery, EmployeeTelegramAccount, TelegramLinkCode, WorkDay

logger = logging.getLogger(__name__)
UTC_PLUS_5 = datetime_timezone(timedelta(hours=5), name='UTC+5')


def employee_name(user):
    return (user.get_full_name() or user.email).strip()


def office_name(workday):
    return str(workday.office) if workday.office_id else 'Без офиса'


def local_time(value):
    if not value:
        return '—'
    if timezone.is_naive(value):
        value = timezone.make_aware(value, UTC_PLUS_5)
    return value.astimezone(UTC_PLUS_5).strftime('%H:%M')


def utc5_today():
    return timezone.now().astimezone(UTC_PLUS_5).date()


def workday_message(workday, event_type):
    name = employee_name(workday.employee)
    office = office_name(workday)
    date_text = workday.date.strftime('%d.%m.%Y')
    if event_type == AttendanceTelegramDelivery.EVENT_ARRIVAL:
        return f'#приход\n{name}\nОфис: {office}\nДата: {date_text}\nНачало: {local_time(workday.started_at)} (UTC+5)'
    if event_type == AttendanceTelegramDelivery.EVENT_DEPARTURE:
        return f'#уход\n{name}\nОфис: {office}\nДата: {date_text}\nЗавершение: {local_time(workday.closed_at)} (UTC+5)'
    if event_type == AttendanceTelegramDelivery.EVENT_AUTO_CLOSE:
        return (
            f'#автозакрытие\n{name}\nОфис: {office}\nДата: {date_text}\n'
            f'День закрыт системой: {local_time(workday.closed_at)} (UTC+5)'
        )
    if event_type == AttendanceTelegramDelivery.EVENT_MISSED:
        return f'#неявка\n{name}\nОфис: {office}\nДата: {date_text}\nРабочий день не был начат.'
    if event_type == AttendanceTelegramDelivery.EVENT_AFTER_HOURS:
        last_seen = (workday.custom_data or {}).get('after_hours_last_seen_at')
        try:
            last_seen_text = local_time(datetime.fromisoformat(last_seen)) if last_seen else 'после 18:00'
        except (TypeError, ValueError):
            last_seen_text = 'после 18:00'
        return (
            f'#после_работы\n{name}\nОфис: {office}\nДата: {date_text}\n'
            f'Зафиксирована активность в ManagerSL: {last_seen_text} (UTC+5)'
        )
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
    account = EmployeeTelegramAccount.objects.filter(employee=workday.employee, is_active=True).first()
    if account:
        personal, personal_created = AttendanceTelegramDelivery.objects.get_or_create(
            event_key=f'personal:{event_key}',
            defaults={
                'event_type': event_type,
                'company': workday.company,
                'office': workday.office,
                'employee': workday.employee,
                'workday': workday,
                'target_chat_id': account.chat_id,
                'message': f'Личное уведомление ManagerSL\n\n{workday_message(workday, event_type)}',
            },
        )
        if personal_created:
            _enqueue(personal)
    return delivery


def send_telegram_message(message, chat_id=None):
    token = settings.ATTENDANCE_TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.ATTENDANCE_TELEGRAM_CHAT_ID
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
        sent, error = send_telegram_message(delivery.message, delivery.target_chat_id)
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


def create_employee_link(user, lifetime_minutes=10):
    raw_code = secrets.token_urlsafe(24)
    TelegramLinkCode.objects.create(
        employee=user,
        code_hash=hashlib.sha256(raw_code.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(minutes=lifetime_minutes),
    )
    username = settings.ATTENDANCE_TELEGRAM_BOT_USERNAME.lstrip('@')
    return f'https://t.me/{username}?start={raw_code}'


def register_personal_reminder(user, reminder_type, day):
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return None
    account = EmployeeTelegramAccount.objects.filter(employee=user, is_active=True).first()
    profile = getattr(user, 'employee_profile', None)
    if not account or not profile:
        return None
    if reminder_type == 'start_workday':
        event_type = AttendanceTelegramDelivery.EVENT_START_REMINDER
        message = '#напоминание_начало\nРабочий день начинается в 09:00 (UTC+5). Войдите в ManagerSL — день откроется автоматически.'
    elif reminder_type == 'close_workday':
        event_type = AttendanceTelegramDelivery.EVENT_CLOSE_REMINDER
        message = '#напоминание_уход\nРабочий день заканчивается в 18:00 (UTC+5). Заполните короткий отчёт и закройте день.'
    elif reminder_type == 'daily_report':
        event_type = AttendanceTelegramDelivery.EVENT_REPORT_REMINDER
        message = '#напоминание_отчёт\n17:30 (UTC+5). До завершения рабочего дня осталось 30 минут. Заполните короткий отчёт в ManagerSL.'
    else:
        return None
    delivery, created = AttendanceTelegramDelivery.objects.get_or_create(
        event_key=f'personal-reminder:{user.pk}:{day}:{event_type}',
        defaults={
            'event_type': event_type,
            'company': profile.company,
            'office': profile.office,
            'employee': user,
            'target_chat_id': account.chat_id,
            'message': message,
        },
    )
    if created:
        _enqueue(delivery)
    return delivery


def register_group_reminder(company, reminder_type, day):
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return None
    if reminder_type == 'daily_report':
        event_type = AttendanceTelegramDelivery.EVENT_REPORT_REMINDER
        message = '#напоминание_отчёт\n17:30 (UTC+5). До конца рабочего дня 30 минут: заполните короткий отчёт в ManagerSL.'
    else:
        return None
    delivery, created = AttendanceTelegramDelivery.objects.get_or_create(
        event_key=f'group-reminder:{company.pk}:{day}:{event_type}',
        defaults={
            'event_type': event_type,
            'company': company,
            'message': message,
        },
    )
    if created:
        _enqueue(delivery)
    return delivery


def queue_admin_message(user, message='', *, is_test=False):
    profile = getattr(user, 'employee_profile', None)
    company = profile.company if profile else Company.objects.filter(is_active=True).order_by('pk').first()
    if not company:
        raise ValueError('Не найдена активная компания для отправки сообщения.')
    clean_message = ' '.join(str(message or '').split()).strip()
    if is_test:
        clean_message = clean_message or 'Тестовое уведомление: связь с ботом ManagerSL работает.'
    if not clean_message:
        raise ValueError('Введите текст сообщения.')
    if len(clean_message) > 500:
        raise ValueError('Сообщение не должно превышать 500 символов.')
    tag = '#тест_бота' if is_test else '#сообщение_руководителя'
    sender = employee_name(user)
    sent_time = timezone.now().astimezone(UTC_PLUS_5).strftime('%d.%m.%Y %H:%M')
    delivery = AttendanceTelegramDelivery.objects.create(
        event_key=f'admin-message:{uuid4().hex}',
        event_type=AttendanceTelegramDelivery.EVENT_ADMIN_MESSAGE,
        company=company,
        office=profile.office if profile and profile.office_id else None,
        employee=user,
        message=f'{tag}\n{clean_message}\n\nОтправил: {sender}\n{sent_time} (UTC+5)',
    )
    _enqueue(delivery)
    return delivery


def _summary_period(today):
    # The company works Monday-Saturday. On Sunday report the week ending yesterday.
    period_end = today - timedelta(days=1) if today.weekday() == 6 else today
    period_start = period_end - timedelta(days=period_end.weekday())
    return period_start, period_end


def _split_summary(lines, header):
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
    if current:
        messages.append(current)
    return messages


def daily_summary_messages(company, report_date=None):
    report_date = report_date or utc5_today()
    profiles = list(
        EmployeeProfile.objects.select_related('user', 'office', 'access').filter(
            company=company,
            is_active=True,
            user__is_active=True,
            hire_date__lte=report_date,
        ).exclude(
            Q(user__is_superuser=True) | Q(user__role='admin')
        ).order_by(
            'office__city', 'office__name', 'user__first_name', 'user__last_name', 'user__email'
        )
    )
    workdays = {
        row.employee_id: row
        for row in WorkDay.objects.filter(
            company=company,
            date=report_date,
            employee_id__in=[profile.user_id for profile in profiles],
        )
    }
    started = []
    not_started = []
    for profile in profiles:
        row = workdays.get(profile.user_id)
        label = employee_name(profile.user)
        office = str(profile.office) if profile.office_id else 'Без офиса'
        if row and row.started_at:
            started.append(f'• {label} — {local_time(row.started_at)} (UTC+5), {office}')
        else:
            not_started.append(f'• {label} — {office}')

    header = f'#учёт_сегодня\n{company.name}\n{report_date:%d.%m.%Y} · время UTC+5'
    lines = [header, f'\n✅ Начали рабочий день — {len(started)}']
    lines.extend(started or ['• Никто'])
    lines.append(f'\n⚪ Ещё не начали — {len(not_started)}')
    lines.extend(not_started or ['• Все отметились'])
    return _split_summary(lines, header)


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
        user__is_active=True,
        hire_date__lte=period_end,
    ).exclude(
        Q(user__is_superuser=True) | Q(user__role='admin')
    ).order_by(
        'office__city', 'office__name', 'user__first_name', 'user__last_name', 'user__email'
    )
    workdays = {
        (row.employee_id, row.date): row
        for row in WorkDay.objects.filter(company=company, date__range=(period_start, period_end))
    }
    grouped = {}
    for profile in profiles:
        grouped.setdefault(str(profile.office) if profile.office_id else 'Без офиса', []).append(profile)

    header = f'#недельный_отчёт\n{company.name}\n{period_start:%d.%m.%Y}–{period_end:%d.%m.%Y}\nЧасовой пояс: UTC+5'
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

    return _split_summary(lines, header)


@shared_task(name='attendance.send_daily_summary')
def send_daily_attendance_summary():
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return {'created': 0, 'reason': 'disabled'}
    today = utc5_today()
    created = 0
    for company in Company.objects.filter(is_active=True):
        for index, message in enumerate(daily_summary_messages(company, today), 1):
            delivery, was_created = AttendanceTelegramDelivery.objects.get_or_create(
                event_key=f'daily:{company.pk}:{today}:{index}',
                defaults={
                    'event_type': AttendanceTelegramDelivery.EVENT_DAILY,
                    'company': company,
                    'message': message,
                },
            )
            if was_created:
                created += 1
                _enqueue(delivery)
    return {'created': created, 'date': str(today)}


@shared_task(name='attendance.send_weekly_summary')
def send_weekly_attendance_summary():
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return {'created': 0, 'reason': 'disabled'}
    today = utc5_today()
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
