"""Киоск-планшет: сканирование QR-бейджей для отметки рабочего дня.

Планшет сканирует статический QR с бейджа сотрудника, событие попадает в
офлайн-очередь на устройстве и синхронизируется в фоне. Сервер идемпотентен
по event_uuid, который планшет генерирует при создании события.
"""

from datetime import timezone as dt_timezone
from io import BytesIO
import secrets

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.permissions import get_employee_profile

from .models import CheckinEvent, KioskBadge, KioskDevice, WorkDay
from .services import should_track_employee

BADGE_CODE_PREFIX = 'SL1'
SYNC_DELAY_FLAG_SECONDS = 300  # задержка синхронизации > 5 минут — помечаем событие

START_RESULTS = {CheckinEvent.RESULT_STARTED, CheckinEvent.RESULT_CLOSED}


def generate_badge_token() -> str:
    return secrets.token_urlsafe(18)


def build_badge_code(badge: KioskBadge) -> str:
    return f'{BADGE_CODE_PREFIX}.{badge.employee_id}.{badge.token}'


def issue_badge(user) -> KioskBadge:
    badge, _ = KioskBadge.objects.get_or_create(
        employee=user,
        defaults={'token': generate_badge_token()},
    )
    return badge


def regenerate_badge(user) -> KioskBadge:
    badge = issue_badge(user)
    badge.token = generate_badge_token()
    badge.is_active = True
    badge.issued_at = timezone.now()
    badge.save(update_fields=['token', 'is_active', 'issued_at', 'updated_at'])
    return badge


def resolve_badge(code: str) -> KioskBadge | None:
    parts = (code or '').strip().split('.')
    if len(parts) != 3 or parts[0] != BADGE_CODE_PREFIX:
        return None
    _, user_id, token = parts
    if not user_id.isdigit() or not token:
        return None
    return (
        KioskBadge.objects
        .select_related('employee')
        .filter(employee_id=user_id, token=token, is_active=True, employee__is_active=True)
        .first()
    )


def badge_qr_svg(code: str) -> str:
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError as exc:
        raise ImproperlyConfigured('Для печати бейджей установите пакет qrcode (pip install qrcode).') from exc
    image = qrcode.make(code, image_factory=SvgPathImage, box_size=12)
    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode('utf-8')


def authenticate_kiosk_device(request) -> KioskDevice | None:
    token = request.headers.get('X-Kiosk-Token', '').strip()
    if not token:
        return None
    return KioskDevice.objects.filter(token=token, is_active=True).first()


def touch_device(device: KioskDevice) -> None:
    KioskDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
    device.last_seen_at = timezone.now()


def parse_device_time(value) -> timezone.datetime | None:
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def process_checkin(*, device: KioskDevice, code: str, event_uuid, device_time=None) -> tuple[CheckinEvent, bool]:
    """Создаёт отметку. Возвращает (событие, создано_сейчас).

    Повторная отправка с тем же event_uuid возвращает ранее сохранённое
    событие без повторного изменения рабочего дня.
    """
    with transaction.atomic():
        existing = (
            CheckinEvent.objects
            .select_for_update()
            .filter(event_uuid=event_uuid)
            .first()
        )
        if existing is not None:
            return existing, False

        now = timezone.now()
        event = CheckinEvent(
            event_uuid=event_uuid,
            device=device,
            code=(code or '')[:128],
            device_time=device_time,
        )
        if device_time is not None:
            event.sync_delay_seconds = max(0, int((now - device_time).total_seconds()))

        badge = resolve_badge(code)
        if badge is None:
            event.result = CheckinEvent.RESULT_INVALID_CODE
            event.message = 'Код не распознан. Обратитесь к руководителю.'
            event.save()
            return event, True

        user = badge.employee
        event.employee = user
        if not should_track_employee(user):
            event.result = CheckinEvent.RESULT_UNTRACKED
            event.message = 'Для этого сотрудника учёт рабочего дня не включён.'
            event.save()
            return event, True

        employee = get_employee_profile(user)
        today = timezone.localdate()
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
        event.workday = workday

        if workday.status in {WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED}:
            event.result = CheckinEvent.RESULT_ALREADY_CLOSED
            event.message = 'Рабочий день уже завершён.'
        elif not workday.started_at or workday.status in {WorkDay.STATUS_NOT_STARTED, WorkDay.STATUS_MISSED}:
            workday.start(note=f'Киоск «{device.name}».')
            event.result = CheckinEvent.RESULT_STARTED
            event.message = f'{user.get_full_name() or user.email}, день начат.'
        else:
            comment = f'Киоск «{device.name}».'
            if workday.report_required and not workday.has_report:
                comment += ' Дневной отчёт не отправлен.'
            workday.close(user=user, comment=comment)
            event.result = CheckinEvent.RESULT_CLOSED
            event.message = f'{user.get_full_name() or user.email}, день закрыт. Хорошего вечера!'

        if event.sync_delay_seconds > SYNC_DELAY_FLAG_SECONDS and event.result in START_RESULTS:
            event.message += ' (офлайн-отметка, синхронизировано поздно)'
        event.save()
    return event, True
