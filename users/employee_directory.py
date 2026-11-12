import secrets

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from apps.employees.models import EmployeeProfile


DEFAULT_LIMIT = 100
MAX_LIMIT = 200


def _authorized(request) -> bool:
    configured = str(getattr(settings, 'EMPLOYEE_DIRECTORY_SERVICE_TOKEN', '') or '').strip()
    supplied = request.headers.get('Authorization', '')
    if not configured or not supplied.startswith('Bearer '):
        return False
    return secrets.compare_digest(supplied.removeprefix('Bearer ').strip(), configured)


def _error(detail: str, status: int):
    response = JsonResponse({'detail': detail}, status=status)
    response['Cache-Control'] = 'private, no-store'
    return response


def _positive_int(value, *, default=None, maximum=None):
    if value in (None, ''):
        return default
    parsed = int(value)
    if parsed < 1:
        raise ValueError
    return min(parsed, maximum) if maximum else parsed


def _object_summary(value, *fields):
    if value is None:
        return None
    return {'id': value.pk, **{field: getattr(value, field) for field in fields}}


def serialize_employee(profile: EmployeeProfile) -> dict:
    user = profile.user
    return {
        'id': profile.pk,
        'user_id': user.pk,
        'email': user.email.lower(),
        'first_name': user.first_name,
        'last_name': user.last_name,
        'middle_name': user.middle_name,
        'display_name': user.get_full_name().strip() or user.email,
        'is_active': bool(user.is_active and profile.is_active),
        'work_status': profile.work_status,
        'hire_date': profile.hire_date.isoformat() if profile.hire_date else None,
        'company': _object_summary(profile.company, 'name'),
        'office': _object_summary(profile.office, 'name', 'city'),
        'department': _object_summary(profile.department, 'name'),
        'position': _object_summary(profile.position, 'name'),
        'role': {
            'id': profile.role_id,
            'code': profile.role.code,
            'name': profile.role.name,
            'type': profile.role.role_type,
        },
        'updated_at': max(profile.updated_at, user.updated_at).isoformat(),
    }


def employee_queryset():
    return EmployeeProfile.objects.select_related(
        'user', 'company', 'office', 'department', 'position', 'role',
    ).order_by('pk')


@require_GET
def employee_directory(request):
    if not _authorized(request):
        return _error('Authentication failed', 401)

    queryset = employee_queryset()
    status_filter = request.GET.get('status', 'active').strip().lower()
    if status_filter == 'active':
        queryset = queryset.filter(user__is_active=True, is_active=True).exclude(work_status__in={'fired', 'paused'})
    elif status_filter != 'all':
        return _error('status must be active or all', 400)

    try:
        company_id = _positive_int(request.GET.get('company_id'))
        office_id = _positive_int(request.GET.get('office_id'))
        cursor = _positive_int(request.GET.get('cursor'), default=0)
        limit = _positive_int(request.GET.get('limit'), default=DEFAULT_LIMIT, maximum=MAX_LIMIT)
    except (TypeError, ValueError):
        return _error('Invalid numeric filter', 400)

    if company_id:
        queryset = queryset.filter(company_id=company_id)
    if office_id:
        queryset = queryset.filter(office_id=office_id)

    updated_after = request.GET.get('updated_after', '').strip()
    if updated_after:
        parsed = parse_datetime(updated_after)
        if parsed is None:
            return _error('updated_after must be an ISO-8601 datetime', 400)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        queryset = queryset.filter(Q(updated_at__gt=parsed) | Q(user__updated_at__gt=parsed))

    total = queryset.count()
    page = list(queryset.filter(pk__gt=cursor)[:limit + 1])
    has_more = len(page) > limit
    page = page[:limit]
    response = JsonResponse({
        'schema_version': 1,
        'count': total,
        'next_cursor': page[-1].pk if has_more and page else None,
        'results': [serialize_employee(profile) for profile in page],
    })
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
def employee_directory_detail(request, user_id: int):
    if not _authorized(request):
        return _error('Authentication failed', 401)
    profile = employee_queryset().filter(user_id=user_id).first()
    if profile is None:
        return _error('Employee not found', 404)
    response = JsonResponse({'schema_version': 1, 'employee': serialize_employee(profile)})
    response['Cache-Control'] = 'private, no-store'
    return response
