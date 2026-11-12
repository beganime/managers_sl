"""Уведомления администраторам о каждом новом сгенерированном документе."""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='erp_documents.GeneratedDocument')
def notify_admins_on_document_created(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.status == instance.STATUS_ERROR:
        return
    from .tasks import notify_document_admins

    document_id = instance.pk
    transaction.on_commit(lambda: _safe_delay(notify_document_admins, document_id))


def _safe_delay(task, document_id) -> None:
    try:
        task.delay(document_id)
    except Exception:
        logger.warning('Could not enqueue %s for document %s.', task.name, document_id)
