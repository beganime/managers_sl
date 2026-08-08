from celery import shared_task

from .services import (
    import_public_client_statuses,
    sync_pending_submissions,
    sync_reference_data,
    sync_submission,
)


@shared_task(name='sheets_sync.sync_reference_data')
def sync_reference_data_task():
    return sync_reference_data()


@shared_task(name='sheets_sync.sync_pending_submissions')
def sync_pending_submissions_task(limit=100):
    return sync_pending_submissions(limit=limit)


@shared_task(name='sheets_sync.import_public_client_statuses')
def import_public_client_statuses_task(limit=1000):
    return import_public_client_statuses(limit=limit)


@shared_task(name='sheets_sync.sync_submission')
def sync_submission_task(submission_id):
    return sync_submission(submission_id)
