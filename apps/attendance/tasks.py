"""Celery task discovery entrypoint for attendance integrations."""

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
