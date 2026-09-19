import hashlib
import hmac
import json
import secrets
import time

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


DISK_SSO_PREFIX = 's1'
DISK_SSO_MAX_AGE_SECONDS = 90


def issue_disk_sso_ticket(email: str, *, issued_at: int | None = None) -> str:
    """Return a short, user-bound ticket accepted by SFTPGo's bcrypt layer."""
    timestamp = int(time.time() if issued_at is None else issued_at)
    normalized_email = str(email or '').strip().lower()
    message = f'{DISK_SSO_PREFIX}:{timestamp}:{normalized_email}'.encode()
    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()[:32]
    return f'{DISK_SSO_PREFIX}.{timestamp}.{signature}'


def verify_disk_sso_ticket(email: str, ticket: str, *, now: int | None = None) -> bool:
    try:
        prefix, raw_timestamp, supplied_signature = ticket.split('.', 2)
        timestamp = int(raw_timestamp)
    except (AttributeError, TypeError, ValueError):
        return False

    current_timestamp = int(time.time() if now is None else now)
    age = current_timestamp - timestamp
    if prefix != DISK_SSO_PREFIX or age < 0 or age > DISK_SSO_MAX_AGE_SECONDS:
        return False

    expected = issue_disk_sso_ticket(email, issued_at=timestamp)
    return secrets.compare_digest(ticket, expected)


def can_access_disk(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', True) or not user.is_active:
        return False

    if user.is_superuser or user.role == 'admin':
        return True

    employee = getattr(user, 'employee_profile', None)
    if employee:
        return bool(
            employee.is_active
            and employee.work_status not in {'fired', 'paused'}
            and employee.role_id
            and employee.role.role_type in {'company_owner', 'office_director', 'manager'}
        )

    # Legacy manager accounts may not have an EmployeeProfile yet.
    return user.role == 'manager'


def _service_token_is_valid(request) -> bool:
    configured = settings.DISK_AUTH_SERVICE_TOKEN
    if not configured:
        return False
    supplied = request.headers.get('Authorization', '')
    prefix = 'Bearer '
    if not supplied.startswith(prefix):
        return False
    return secrets.compare_digest(supplied[len(prefix):], configured)


@csrf_exempt
@require_POST
def disk_authenticate(request):
    """Authenticate a ManagerSL employee for the private document disk."""
    if not _service_token_is_valid(request):
        return JsonResponse({'detail': 'Forbidden'}, status=403)

    try:
        payload = json.loads(request.body or b'{}')
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    email = str(payload.get('username') or '').strip()
    password = str(payload.get('password') or '')
    if not email or not password or len(email) > 254 or len(password) > 512:
        return JsonResponse({'authenticated': False}, status=401)

    user = None
    if password.startswith(f'{DISK_SSO_PREFIX}.'):
        if verify_disk_sso_ticket(email, password):
            user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    else:
        user = authenticate(request=request, email=email, password=password)
    if not can_access_disk(user):
        return JsonResponse({'authenticated': False}, status=401)

    return JsonResponse({
        'authenticated': True,
        'username': user.email,
        'display_name': user.get_full_name().strip() or user.email,
    })
