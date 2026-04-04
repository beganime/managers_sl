import json
import os

from django.conf import settings

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:  # pragma: no cover
    firebase_admin = None
    credentials = None
    messaging = None


def get_firebase_app():
    if firebase_admin is None:
        return None

    try:
        return firebase_admin.get_app()
    except Exception:
        pass

    file_path = getattr(settings, 'FCM_CREDENTIALS_FILE', '') or os.getenv('FCM_CREDENTIALS_FILE', '')
    json_blob = getattr(settings, 'FCM_CREDENTIALS_JSON', '') or os.getenv('FCM_CREDENTIALS_JSON', '')

    if file_path:
        cred = credentials.Certificate(file_path)
        return firebase_admin.initialize_app(cred)

    if json_blob:
        cred = credentials.Certificate(json.loads(json_blob))
        return firebase_admin.initialize_app(cred)

    return None


def send_push_to_tokens(tokens, title, body, data=None):
    app = get_firebase_app()
    if app is None or messaging is None:
        return {'success_count': 0, 'failure_count': len(tokens), 'results': [], 'detail': 'Firebase не настроен'}

    if not tokens:
        return {'success_count': 0, 'failure_count': 0, 'results': []}

    message = messaging.MulticastMessage(
        tokens=list(tokens),
        notification=messaging.Notification(title=title, body=body),
        data={str(k): str(v) for k, v in (data or {}).items()},
    )
    response = messaging.send_each_for_multicast(message, app=app)

    results = []
    for idx, item in enumerate(response.responses):
        results.append(
            {
                'token': tokens[idx],
                'success': item.success,
                'message_id': getattr(item, 'message_id', None),
                'exception': str(item.exception) if item.exception else None,
            }
        )

    return {
        'success_count': response.success_count,
        'failure_count': response.failure_count,
        'results': results,
    }