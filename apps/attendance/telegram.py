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

from .models import (
    AttendanceTelegramDelivery,
    AttendanceTelegramTopic,
    EmployeeTelegramAccount,
    TelegramLinkCode,
    WorkDay,
    WorkSession,
)
from .services import attendance_profile_q

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
            last_seen_text = local_time(datetime.fromisoformat(last_seen)) if last_seen else 'после 20:00'
        except (TypeError, ValueError):
            last_seen_text = 'после 20:00'
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


def topic_type_for_event(event_type):
    if event_type == AttendanceTelegramDelivery.EVENT_DAILY:
        return AttendanceTelegramTopic.TOPIC_DAILY
    if event_type == AttendanceTelegramDelivery.EVENT_MISSED:
        return AttendanceTelegramTopic.TOPIC_ABSENT
    if event_type in {
        AttendanceTelegramDelivery.EVENT_ARRIVAL,
        AttendanceTelegramDelivery.EVENT_DEPARTURE,
        AttendanceTelegramDelivery.EVENT_AUTO_CLOSE,
        AttendanceTelegramDelivery.EVENT_AFTER_HOURS,
        AttendanceTelegramDelivery.EVENT_START_REMINDER,
        AttendanceTelegramDelivery.EVENT_CLOSE_REMINDER,
    }:
        return AttendanceTelegramTopic.TOPIC_TIME
    return AttendanceTelegramTopic.TOPIC_REPORTS


def resolve_group_topic(event_type, chat_id=None):
    raw_chat_id = chat_id or settings.ATTENDANCE_TELEGRAM_CHAT_ID
    if not raw_chat_id:
        return None
    try:
        chat_id = int(raw_chat_id)
    except (TypeError, ValueError):
        return None
    topic_type = topic_type_for_event(event_type)
    topic = AttendanceTelegramTopic.objects.filter(
        chat_id=chat_id,
        topic_type=topic_type,
    ).first()
    if topic:
        return topic
    # A forum conversion changes the Telegram chat id. Once the new forum has
    # been explicitly configured with /topic, it becomes the authoritative
    # destination even while the old numeric id remains in the environment.
    candidates = list(AttendanceTelegramTopic.objects.filter(topic_type=topic_type)[:2])
    return candidates[0] if len(candidates) == 1 else None


def send_telegram_message(message, chat_id=None, message_thread_id=None):
    token = settings.ATTENDANCE_TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.ATTENDANCE_TELEGRAM_CHAT_ID
    if not settings.ATTENDANCE_TELEGRAM_ENABLED or not token or not chat_id:
        return False, 'Telegram attendance is not configured.'
    base = settings.ATTENDANCE_TELEGRAM_API_BASE.rstrip('/')
    try:
        payload = {'chat_id': chat_id, 'text': message, 'disable_web_page_preview': True}
        if message_thread_id:
            payload['message_thread_id'] = int(message_thread_id)
        response = requests.post(
            f'{base}/bot{token}/sendMessage',
            json=payload,
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
        target_chat_id = delivery.target_chat_id
        target_thread_id = delivery.target_message_thread_id
        if not target_chat_id:
            topic = resolve_group_topic(delivery.event_type)
            if not topic:
                sent, error = False, f'telegram_topic_not_configured:{topic_type_for_event(delivery.event_type)}'
            else:
                target_chat_id = topic.chat_id
                target_thread_id = topic.message_thread_id
                sent, error = send_telegram_message(delivery.message, target_chat_id, target_thread_id)
                delivery.target_chat_id = target_chat_id
                delivery.target_message_thread_id = target_thread_id
        else:
            sent, error = send_telegram_message(delivery.message, target_chat_id, target_thread_id)
        delivery.status = AttendanceTelegramDelivery.STATUS_SENT if sent else AttendanceTelegramDelivery.STATUS_FAILED
        delivery.last_error = error[:255]
        delivery.sent_at = timezone.now() if sent else None
        delivery.save(update_fields=[
            'attempts', 'status', 'last_error', 'sent_at', 'target_chat_id',
            'target_message_thread_id', 'updated_at',
        ])
    return {'sent': sent}


@shared_task(name='attendance.retry_telegram_deliveries')
def retry_attendance_telegram_deliveries(limit=50):
    ids = list(
        AttendanceTelegramDelivery.objects.filter(
            status__in=[AttendanceTelegramDelivery.STATUS_PENDING, AttendanceTelegramDelivery.STATUS_FAILED],
            attempts__lt=5,
        ).filter(
            Q(target_chat_id__isnull=False) | Q(created_at__gte=timezone.now() - timedelta(hours=2))
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


def report_message(report):
    submitted = (report.submitted_at or report.updated_at).astimezone(UTC_PLUS_5).strftime('%d.%m.%Y %H:%M')
    office = str(report.office) if report.office_id else 'Без офиса'
    parts = [
        '#отчёт_сотрудника',
        employee_name(report.employee),
        f'Офис: {office}',
        f'Отправлен: {submitted} (UTC+5)',
        '',
        report.content.strip(),
    ]
    if report.results.strip():
        parts.extend(['', f'Итоги: {report.results.strip()}'])
    if report.plans.strip():
        parts.extend(['', f'Планы: {report.plans.strip()}'])
    if report.problems.strip():
        parts.extend(['', f'Проблемы: {report.problems.strip()}'])
    return '\n'.join(parts)[:3900]


def register_report_event(report):
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return None
    delivery, created = AttendanceTelegramDelivery.objects.get_or_create(
        event_key=f'report:{report.pk}:{report.updated_at.isoformat()}',
        defaults={
            'event_type': AttendanceTelegramDelivery.EVENT_REPORT_SUBMITTED,
            'company': report.company,
            'office': report.office,
            'employee': report.employee,
            'workday': report.workday,
            'message': report_message(report),
        },
    )
    if created:
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


def daily_summary_messages(company, report_date=None, *, catchup=False):
    report_date = report_date or utc5_today()
    historical = report_date < utc5_today()
    profiles = list(
        EmployeeProfile.objects.select_related('user', 'office', 'access').filter(
            attendance_profile_q(), company=company, hire_date__lte=report_date,
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
    active_employee_ids = set()
    if not historical:
        active_employee_ids = set(
            WorkSession.objects.filter(
                workday__company=company,
                workday__date=report_date,
                is_active=True,
            ).values_list('employee_id', flat=True)
        )
    started = []
    working_now = []
    finished = []
    not_started = []
    report_count = 0
    for profile in profiles:
        row = workdays.get(profile.user_id)
        label = employee_name(profile.user)
        office = str(profile.office) if profile.office_id else 'Без офиса'
        if row and row.started_at:
            started.append(f'• {label} — {local_time(row.started_at)} (UTC+5), {office}')
            if profile.user_id in active_employee_ids:
                working_now.append(f'• {label} — {office}')
            if row.status in {WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED}:
                finished.append(f'• {label} — {local_time(row.closed_at)} (UTC+5), {office}')
            if row.has_report:
                report_count += 1
        else:
            not_started.append(f'• {label} — {office}')

    if catchup:
        prepared = timezone.now().astimezone(UTC_PLUS_5).strftime('%d.%m.%Y %H:%M')
        header = f'#итоги_дня #повторная_сводка\n{company.name}\nЗа {report_date:%d.%m.%Y} · составлена {prepared} UTC+5'
    else:
        header = f'#итоги_дня\n{company.name}\n{report_date:%d.%m.%Y} · 18:00 · UTC+5'
    lines = [
        header,
        '',
        f'Всего сотрудников для учёта: {len(profiles)}',
        f'Вышли на работу: {len(started)}',
        f'Уже завершили день: {len(finished)}',
        f'Не вышли: {len(not_started)}',
        f'Отчёты отправили: {report_count}',
        f'Отчёты ожидаются: {max(len(started) - report_count, 0)}',
        f'\n✅ Вышли на работу — {len(started)}',
    ]
    if not historical:
        lines.insert(4, f'Сейчас работают: {len(working_now)}')
    lines.extend(started or ['• Никто'])
    if not historical:
        lines.append(f'\n🟢 Сейчас на работе — {len(working_now)}')
        lines.extend(working_now or ['• Никого'])
    lines.append(f'\n🔴 Не вышли — {len(not_started)}')
    lines.extend(not_started or ['• Все вышли'])
    return _split_summary(lines, header)


def queue_recent_attendance_catchup():
    """Send yesterday/today once to the configured daily topic, never General."""
    if not getattr(settings, 'ATTENDANCE_TELEGRAM_ENABLED', False):
        return {'created': 0, 'reason': 'disabled'}
    topic = resolve_group_topic(AttendanceTelegramDelivery.EVENT_DAILY)
    if not topic:
        return {'created': 0, 'reason': 'daily_topic_not_configured'}
    today = utc5_today()
    workdays = set(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5)))
    dates = [day for day in (today - timedelta(days=1), today) if day.weekday() in workdays]
    created = 0
    existing = 0
    for company in Company.objects.filter(is_active=True):
        for day in dates:
            for index, message in enumerate(daily_summary_messages(company, day, catchup=True), 1):
                delivery, was_created = AttendanceTelegramDelivery.objects.get_or_create(
                    event_key=f'catchup-daily:{company.pk}:{day}:{index}',
                    defaults={
                        'event_type': AttendanceTelegramDelivery.EVENT_DAILY,
                        'company': company,
                        'message': message,
                        'target_chat_id': topic.chat_id,
                        'target_message_thread_id': topic.message_thread_id,
                    },
                )
                if was_created:
                    _enqueue(delivery)
                    created += 1
                else:
                    existing += 1
    return {'created': created, 'existing': existing, 'dates': [day.isoformat() for day in dates]}


def weekly_summary_messages(company, period_start, period_end):
    weekdays = set(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5)))
    dates = [
        period_start + timedelta(days=offset)
        for offset in range((period_end - period_start).days + 1)
        if (period_start + timedelta(days=offset)).weekday() in weekdays
    ]
    profiles = EmployeeProfile.objects.select_related('user', 'office', 'access').filter(
        attendance_profile_q(), company=company, hire_date__lte=period_end,
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
    if today.weekday() not in set(getattr(settings, 'ATTENDANCE_WORKDAYS', (0, 1, 2, 3, 4, 5))):
        return {'created': 0, 'date': str(today), 'reason': 'non_working_day'}
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
