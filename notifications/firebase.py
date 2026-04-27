import logging
import os
from typing import Iterable

from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import FCMDevice

logger = logging.getLogger(__name__)

_firebase_ready = False
_firebase_error_logged = False


def _init_firebase():
    global _firebase_ready, _firebase_error_logged

    if _firebase_ready:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_ready = True
            return True

        cred_path = (
            os.environ.get('FIREBASE_CREDENTIALS_PATH')
            or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        )

        if not cred_path:
            if not _firebase_error_logged:
                logger.warning('Firebase credentials path is not configured.')
                _firebase_error_logged = True
            return False

        firebase_admin.initialize_app(credentials.Certificate(cred_path))
        _firebase_ready = True
        return True
    except Exception:
        if not _firebase_error_logged:
            logger.exception('Firebase initialization failed.')
            _firebase_error_logged = True
        return False


def send_push_to_tokens(tokens: Iterable[str], title: str, body: str, data: dict | None = None) -> int:
    tokens = [str(token).strip() for token in tokens if str(token or '').strip()]
    if not tokens:
        return 0

    if not _init_firebase():
        return 0

    try:
        from firebase_admin import messaging

        sent = 0
        for token in tokens:
            message = messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                data={str(k): str(v) for k, v in (data or {}).items()},
            )
            try:
                messaging.send(message)
                sent += 1
            except Exception:
                logger.exception('Failed to send Firebase push to token.')
                FCMDevice.objects.filter(token=token).update(is_active=False)
        return sent
    except Exception:
        logger.exception('Firebase send failed.')
        return 0


def get_admin_push_tokens():
    User = get_user_model()
    admin_ids = User.objects.filter(
        Q(is_superuser=True) | Q(is_staff=True) | Q(role='admin')
    ).values_list('id', flat=True)

    return list(
        FCMDevice.objects.filter(user_id__in=admin_ids, is_active=True)
        .values_list('token', flat=True)
        .distinct()
    )


def notify_admins_about_new_lead(lead):
    tokens = get_admin_push_tokens()
    if not tokens:
        return 0

    title = 'Новая заявка ManagerSL'
    body = f'{lead.full_name or "Новая заявка"} · {lead.phone or "без телефона"}'
    return send_push_to_tokens(
        tokens,
        title,
        body,
        data={
            'type': 'new_lead',
            'lead_id': lead.id,
            'screen': 'leads',
        },
    )