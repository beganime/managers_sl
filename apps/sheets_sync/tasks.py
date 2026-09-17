from celery import shared_task
from googleapiclient.errors import HttpError

from .services import (
    import_onboarding_decisions,
    import_public_client_statuses,
    sync_onboarding_inbox,
    sync_onboarding_submission,
    sync_pending_submissions,
    sync_reference_data,
    sync_submission,
)


SHEETS_TASK_OPTIONS = {
    'autoretry_for': (HttpError,),
    'retry_backoff': 30,
    'retry_jitter': True,
    'retry_kwargs': {'max_retries': 3},
}


@shared_task(name='sheets_sync.sync_reference_data', **SHEETS_TASK_OPTIONS)
def sync_reference_data_task():
    return sync_reference_data()


@shared_task(name='sheets_sync.sync_onboarding_inbox', **SHEETS_TASK_OPTIONS)
def sync_onboarding_inbox_task(limit=1000):
    return sync_onboarding_inbox(limit=limit)


@shared_task(name='sheets_sync.import_onboarding_decisions', **SHEETS_TASK_OPTIONS)
def import_onboarding_decisions_task(limit=1000):
    return import_onboarding_decisions(limit=limit)


@shared_task(name='sheets_sync.sync_onboarding_submission', **SHEETS_TASK_OPTIONS)
def sync_onboarding_submission_task(submission_id, force_status=False):
    return sync_onboarding_submission(submission_id, force_status=force_status)


@shared_task(name='sheets_sync.sync_pending_submissions', **SHEETS_TASK_OPTIONS)
def sync_pending_submissions_task(limit=100):
    return sync_pending_submissions(limit=limit)


@shared_task(name='sheets_sync.import_public_client_statuses', **SHEETS_TASK_OPTIONS)
def import_public_client_statuses_task(limit=1000):
    return import_public_client_statuses(limit=limit)


@shared_task(name='sheets_sync.sync_submission', **SHEETS_TASK_OPTIONS)
def sync_submission_task(submission_id):
    return sync_submission(submission_id)
