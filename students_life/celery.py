import os
import sys

if os.environ.get('CELERY_DISABLE_GSSAPI', '1') == '1':
    sys.modules.setdefault('gssapi', None)

from celery import Celery
from celery.schedules import crontab
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'students_life.settings')

app = Celery('students_life')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'erp-send-queued-notifications-every-minute': {
        'task': 'erp_notifications.send_queued_notifications',
        'schedule': crontab(minute='*/1'),
    },
    'erp-auto-close-workdays': {
        'task': 'erp_notifications.auto_close_workdays',
        'schedule': crontab(
            minute=str(settings.ATTENDANCE_AUTO_CLOSE_MINUTE),
            hour=str(settings.ATTENDANCE_AUTO_CLOSE_HOUR),
        ),
    },
    'erp-daily-start-reminders': {
        'task': 'erp_notifications.daily_start_reminder',
        'schedule': crontab(minute='*/5'),
    },
    'erp-daily-report-reminders': {
        'task': 'erp_notifications.daily_report_reminder',
        'schedule': crontab(minute='*/5'),
    },
    'erp-close-workday-reminders': {
        'task': 'erp_notifications.close_workday_reminder',
        'schedule': crontab(minute='*/5'),
    },
    'erp-task-deadline-reminders': {
        'task': 'erp_notifications.task_reminders',
        'schedule': crontab(minute=0),
        'args': (settings.TASK_REMINDER_HOURS_AHEAD,),
    },
    'erp-document-approval-notifications': {
        'task': 'erp_notifications.document_approval_notification',
        'schedule': crontab(minute='*/5'),
    },
    'erp-payment-confirmation-notifications': {
        'task': 'erp_notifications.payment_confirmation_notification',
        'schedule': crontab(minute='*/5'),
    },
    'erp-birthday-reminders': {
        'task': 'erp_notifications.send_birthday_reminders',
        'schedule': crontab(minute=0, hour=8),
    },
    'sheets-sync-pending-submissions': {
        'task': 'sheets_sync.sync_pending_submissions',
        'schedule': crontab(minute='*/1'),
    },
    'sheets-sync-onboarding-inbox': {
        'task': 'sheets_sync.sync_onboarding_inbox',
        'schedule': crontab(minute='*/1'),
    },
    'sheets-import-onboarding-decisions': {
        'task': 'sheets_sync.import_onboarding_decisions',
        'schedule': crontab(minute='*/1'),
    },
    'sheets-sync-reference-data': {
        'task': 'sheets_sync.sync_reference_data',
        'schedule': crontab(minute='*/5'),
    },
    'sheets-import-public-client-statuses': {
        'task': 'sheets_sync.import_public_client_statuses',
        'schedule': crontab(minute='*/1'),
    },
}
