import json
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


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

    user = authenticate(request=request, email=email, password=password)
    if not can_access_disk(user):
        return JsonResponse({'authenticated': False}, status=401)

    return JsonResponse({
        'authenticated': True,
        'username': user.email,
        'display_name': user.get_full_name().strip() or user.email,
    })
