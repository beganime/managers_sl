import json
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from users.disk_auth import can_access_disk


def _service_token_is_valid(request) -> bool:
    configured = str(getattr(settings, 'EXAM_SL_AUTH_SERVICE_TOKEN', '') or '')
    supplied = request.headers.get('Authorization', '')
    if not configured or not supplied.startswith('Bearer '):
        return False
    return secrets.compare_digest(supplied.removeprefix('Bearer ').strip(), configured)


@csrf_exempt
@require_POST
def exam_authenticate(request):
    """Authenticate an ExamSL manager against the canonical ManagerSL user base."""
    if not _service_token_is_valid(request):
        return JsonResponse({'detail': 'Forbidden'}, status=403)

    try:
        payload = json.loads(request.body or b'{}')
    except (TypeError, ValueError, UnicodeDecodeError):
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)

    email = str(payload.get('username') or payload.get('email') or '').strip().lower()
    password = str(payload.get('password') or '')
    if not email or not password or len(email) > 254 or len(password) > 512:
        return JsonResponse({'authenticated': False}, status=401)

    user = authenticate(request=request, email=email, password=password)
    if not can_access_disk(user):
        return JsonResponse({'authenticated': False}, status=401)

    employee = getattr(user, 'employee_profile', None)
    employee_role = ''
    if employee and getattr(employee, 'role_id', None):
        employee_role = employee.role.role_type

    return JsonResponse({
        'authenticated': True,
        'username': user.email.lower(),
        'email': user.email.lower(),
        'first_name': user.first_name,
        'last_name': user.last_name,
        'display_name': user.get_full_name().strip() or user.email,
        'role': user.role,
        'employee_role': employee_role,
        'is_staff': bool(user.is_staff or user.is_superuser or user.role == 'admin'),
    })
