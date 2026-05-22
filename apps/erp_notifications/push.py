import logging
import os

from django.utils import timezone

from .models import DeviceToken, NotificationLog, NotificationTemplate

logger = logging.getLogger(__name__)

_firebase_ready = False
_firebase_error_logged = False


def init_firebase():
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
            or os.environ.get('FCM_CREDENTIALS_FILE')
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


def send_push(notification):
    tokens = list(
        DeviceToken.objects.filter(user=notification.recipient, is_active=True)
        .order_by('-last_seen_at')
        .distinct()
    )
    if not tokens:
        NotificationLog.objects.create(
            notification=notification,
            channel=NotificationTemplate.CHANNEL_PUSH,
            status=NotificationLog.STATUS_SKIPPED,
            provider='firebase',
            recipient=str(notification.recipient_id),
            error_message='No active device tokens.',
        )
        return 0

    if not init_firebase():
        NotificationLog.objects.create(
            notification=notification,
            channel=NotificationTemplate.CHANNEL_PUSH,
            status=NotificationLog.STATUS_FAILED,
            provider='firebase',
            recipient=str(notification.recipient_id),
            error_message='Firebase is not configured.',
        )
        return 0

    from firebase_admin import messaging

    sent = 0
    for device in tokens:
        request_data = {
            'token': device.token,
            'title': notification.title,
            'body': notification.body,
            'data': {str(key): str(value) for key, value in (notification.data or {}).items()},
        }
        try:
            message = messaging.Message(
                token=device.token,
                notification=messaging.Notification(title=notification.title, body=notification.body),
                data=request_data['data'],
            )
            message_id = messaging.send(message)
            sent += 1
            NotificationLog.objects.create(
                notification=notification,
                device_token=device,
                channel=NotificationTemplate.CHANNEL_PUSH,
                status=NotificationLog.STATUS_SUCCESS,
                provider='firebase',
                recipient=device.token[:255],
                request_data=request_data,
                response_data={'message_id': message_id},
                sent_at=timezone.now(),
            )
        except Exception as exc:
            logger.exception('Failed to send Firebase push notification.')
            DeviceToken.objects.filter(pk=device.pk).update(is_active=False)
            NotificationLog.objects.create(
                notification=notification,
                device_token=device,
                channel=NotificationTemplate.CHANNEL_PUSH,
                status=NotificationLog.STATUS_FAILED,
                provider='firebase',
                recipient=device.token[:255],
                request_data=request_data,
                error_message=str(exc),
            )
    return sent
