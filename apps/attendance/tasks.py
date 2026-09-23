"""Celery task discovery entrypoint for attendance integrations."""

from .telegram import (  # noqa: F401
    retry_attendance_telegram_deliveries,
    send_attendance_telegram_delivery,
    send_weekly_attendance_summary,
)
