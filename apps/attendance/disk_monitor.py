import logging

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.organizations.models import Company

from .models import AttendanceTelegramDelivery, EmployeeTelegramAccount
from .telegram import _enqueue, UTC_PLUS_5


logger = logging.getLogger(__name__)


def format_bytes(value) -> str:
    amount = max(int(value or 0), 0)
    units = ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ')
    number = float(amount)
    unit = units[0]
    for unit in units:
        if number < 1024 or unit == units[-1]:
            break
        number /= 1024
    precision = 0 if unit == 'Б' else 1
    return f'{number:.{precision}f} {unit}'


def storage_alert_level(percent) -> str | None:
    value = float(percent or 0)
    if value >= 95:
        return 'critical'
    if value >= 90:
        return 'high'
    if value >= 75:
        return 'warning'
    return None


def _recipient():
    email = str(getattr(settings, 'DISK_MONITOR_RECIPIENT_EMAIL', '') or '').strip().lower()
    if not email:
        return None
    return EmployeeTelegramAccount.objects.select_related(
        'employee', 'employee__employee_profile', 'employee__employee_profile__company',
        'employee__employee_profile__office',
    ).filter(employee__email__iexact=email, employee__is_active=True, is_active=True).first()


def _queue_owner_alert(kind: str, message: str, *, slot: str):
    account = _recipient()
    if account is None:
        return {'queued': False, 'reason': 'recipient_not_connected'}
    user = account.employee
    profile = getattr(user, 'employee_profile', None)
    company = profile.company if profile else Company.objects.filter(is_active=True).order_by('pk').first()
    if company is None:
        return {'queued': False, 'reason': 'company_missing'}
    delivery, created = AttendanceTelegramDelivery.objects.get_or_create(
        event_key=f'disk-monitor:{kind}:{slot}',
        defaults={
            'event_type': AttendanceTelegramDelivery.EVENT_ADMIN_MESSAGE,
            'company': company,
            'office': profile.office if profile and profile.office_id else None,
            'employee': user,
            'target_chat_id': account.chat_id,
            'message': message[:3900],
        },
    )
    if created:
        _enqueue(delivery)
    return {'queued': created, 'delivery_id': delivery.pk}


def _failure_slot(now) -> str:
    local = now.astimezone(UTC_PLUS_5)
    return f'{local:%Y%m%d}-{local.hour // 6}'


def _daily_slot(now) -> str:
    return now.astimezone(UTC_PLUS_5).strftime('%Y%m%d')


def _fetch_monitor_payload():
    endpoint = str(getattr(settings, 'DISK_MONITOR_API_URL', '') or '').strip()
    token = str(getattr(settings, 'DISK_PROVISION_SERVICE_TOKEN', '') or '').strip()
    if not endpoint or not token:
        raise RuntimeError('Disk monitor is not configured')
    response = requests.get(
        endpoint,
        headers={'Authorization': f'Bearer {token}', 'User-Agent': 'manager-sl-disk-monitor/1.0'},
        timeout=(3.05, 8),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError('Invalid DiskSL monitor response')
    return payload


def _summary_message(storage: dict, *, heading: str) -> str:
    percent = float(storage.get('usage_percent') or 0)
    age_seconds = int(storage.get('age_seconds') or 0)
    refreshed = 'только что' if age_seconds < 90 else f'{max(1, age_seconds // 60)} мин. назад'
    return (
        f'{heading}\n\n'
        f'Заполнено: {percent:.1f}%\n'
        f'Занято: {format_bytes(storage.get("used_bytes"))}\n'
        f'Свободно: {format_bytes(storage.get("free_bytes"))}\n'
        f'Настроенный лимит: {format_bytes(storage.get("total_bytes"))}\n'
        f'Объектов: {int(storage.get("objects") or 0)}\n'
        f'Статистика обновлена: {refreshed}\n\n'
        'Лимит берётся из конфигурации DiskSL и не заменяет проверку тарифа S3-провайдера.'
    )


@shared_task(name='attendance.check_disk_health')
def check_disk_health(send_summary=False):
    now = timezone.now()
    try:
        payload = _fetch_monitor_payload()
    except Exception as exc:
        logger.warning('DiskSL monitor request failed: %s', type(exc).__name__)
        return _queue_owner_alert(
            'unavailable',
            '#критично_DiskSL\nDiskSL не ответил на автоматическую проверку. Файлы и внешний вход нужно проверить. Повторные одинаковые уведомления ограничены одним сообщением за 6 часов.',
            slot=_failure_slot(now),
        )

    storage = payload.get('storage')
    if not isinstance(storage, dict):
        return _queue_owner_alert(
            'warming-up',
            '#предупреждение_DiskSL\nDiskSL отвечает, но ещё не подготовил статистику хранилища.',
            slot=_failure_slot(now),
        )

    if payload.get('status') == 'stale' or int(storage.get('age_seconds') or 0) > 900:
        return _queue_owner_alert(
            'stale',
            _summary_message(storage, heading='#предупреждение_DiskSL\nСтатистика S3 не обновлялась больше 15 минут.'),
            slot=_failure_slot(now),
        )

    level = storage_alert_level(storage.get('usage_percent'))
    if level:
        headings = {
            'warning': '#лимит_DiskSL\nХранилище заполнено более чем на 75%.',
            'high': '#важно_DiskSL\nХранилище заполнено более чем на 90%.',
            'critical': '#критично_DiskSL\nХранилище заполнено более чем на 95%.',
        }
        return _queue_owner_alert(
            f'quota-{level}',
            _summary_message(storage, heading=headings[level]),
            slot=_daily_slot(now),
        )

    if send_summary:
        return _queue_owner_alert(
            'daily-summary',
            _summary_message(storage, heading='#DiskSL\nЕжедневная проверка хранилища: всё работает нормально.'),
            slot=_daily_slot(now),
        )
    return {'queued': False, 'reason': 'healthy'}


@shared_task(name='attendance.send_disk_daily_summary')
def send_disk_daily_summary():
    return check_disk_health(send_summary=True)
