"""Celery task discovery entrypoint for attendance integrations."""

from celery import shared_task

from .telegram import (  # noqa: F401
    retry_attendance_telegram_deliveries,
    send_attendance_telegram_delivery,
    send_weekly_attendance_summary,
)
from .weekly_reports import (  # noqa: F401
    cleanup_weekly_report_archives,
    process_weekly_report,
    remind_weekly_reports,
    retry_weekly_report_delivery,
)
from .disk_monitor import check_disk_health, send_disk_daily_summary  # noqa: F401


@shared_task(name='attendance.admin_daily_digest')
def admin_daily_digest():
    from .telegram import register_admin_daily_digest

    return {'created': register_admin_daily_digest()}
