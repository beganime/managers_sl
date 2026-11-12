import secrets
from datetime import datetime, time, timedelta

import requests
from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Avg, Count, F, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Lead, LeadEliteTaskState

User = get_user_model()
LEADERSHIP_ROLES = {'leader', 'admin', 'chief_manager'}


def _authorized(request):
    expected = str(getattr(settings, 'ELITE_TASK_SERVICE_TOKEN', '') or '')
    supplied = request.headers.get('Authorization', '')
    if not expected or not supplied.startswith('Bearer '):
        return False
    return secrets.compare_digest(supplied.removeprefix('Bearer ').strip(), expected)


def _json(request):
    import json

    try:
        return json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return None


def _manager_for(payload):
    email = str(payload.get('email') or '').strip().lower()
    if not email:
        return None
    return User.objects.filter(email__iexact=email, is_active=True).first()


def _elite_task_headers():
    key = str(getattr(settings, 'ELITE_TASK_INTEGRATION_KEY', '') or '')
    if not key:
        raise RuntimeError('ELITE_TASK_INTEGRATION_KEY is not configured')
    return {'X-API-Key': key, 'Content-Type': 'application/json'}


def _elite_task_post(path, payload):
    base = str(getattr(settings, 'ELITE_TASK_API_URL', '') or '').rstrip('/')
    if not base:
        raise RuntimeError('ELITE_TASK_API_URL is not configured')
    response = requests.post(
        f'{base}{path}',
        json=payload,
        headers=_elite_task_headers(),
        timeout=(5, 20),
    )
    response.raise_for_status()
    return response.json()


@shared_task(bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True, retry_jitter=True, max_retries=8)
def publish_lead_to_elite_task(self, lead_id):
    lead = Lead.objects.get(pk=lead_id)
    state, _ = LeadEliteTaskState.objects.get_or_create(lead=lead)
    state.attempts = F('attempts') + 1
    state.status = LeadEliteTaskState.STATUS_PENDING
    state.save(update_fields=['attempts', 'status', 'updated_at'])
    try:
        result = _elite_task_post(
            '/integrations/v1/crm/leads',
            {
                'external_id': str(lead.pk),
                'full_name': lead.full_name,
                'phone': lead.phone or '',
                'email': lead.email or '',
                'direction': lead.get_direction_display() if lead.direction else '',
                'crm_url': f'https://manager-sl.ru/portal/leads/{lead.pk}/',
                'occurred_at': lead.created_at.isoformat(),
            },
        )
    except Exception as exc:
        state.refresh_from_db()
        state.status = LeadEliteTaskState.STATUS_FAILED
        state.last_error = f'{type(exc).__name__}: {str(exc)[:400]}'
        state.save(update_fields=['status', 'last_error', 'updated_at'])
        raise
    state.refresh_from_db()
    state.status = LeadEliteTaskState.STATUS_SENT
    state.elite_task_lead_id = str(result.get('id') or '')
    state.last_error = ''
    state.sent_at = timezone.now()
    state.save(update_fields=['status', 'elite_task_lead_id', 'last_error', 'sent_at', 'updated_at'])
    return {'lead_id': lead_id, 'elite_task_lead_id': state.elite_task_lead_id}


def enqueue_lead_to_elite_task(lead_id):
    try:
        publish_lead_to_elite_task.delay(lead_id)
    except Exception:
        LeadEliteTaskState.objects.update_or_create(
            lead_id=lead_id,
            defaults={'status': LeadEliteTaskState.STATUS_FAILED, 'last_error': 'queue_unavailable'},
        )


@csrf_exempt
@require_POST
def claim_lead(request, lead_id):
    if not _authorized(request):
        return JsonResponse({'detail': 'Authentication failed.'}, status=401)
    payload = _json(request)
    if payload is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    manager = _manager_for(payload)
    if manager is None:
        return JsonResponse({'detail': 'ManagerSL user with this email was not found.'}, status=422)
    with transaction.atomic():
        lead = Lead.objects.select_for_update().filter(pk=lead_id, is_archived=False).first()
        if lead is None:
            return JsonResponse({'detail': 'Lead not found.'}, status=404)
        if lead.manager_id and lead.manager_id != manager.id:
            return JsonResponse(
                {'detail': 'Lead is already claimed.', 'manager': lead.manager.get_full_name() or lead.manager.email},
                status=409,
            )
        if not lead.manager_id:
            lead.manager = manager
            lead.taken_at = lead.taken_at or timezone.now()
            lead.log_action('take_from_elite_task', manager)
            lead.save(update_fields=['manager', 'taken_at', 'custom_data', 'updated_at'])
    return JsonResponse({'ok': True, 'lead_id': lead.pk, 'manager_id': manager.pk})


@csrf_exempt
@require_POST
def process_lead(request, lead_id):
    if not _authorized(request):
        return JsonResponse({'detail': 'Authentication failed.'}, status=401)
    payload = _json(request)
    if payload is None:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    actor = _manager_for(payload)
    if actor is None:
        return JsonResponse({'detail': 'ManagerSL user with this email was not found.'}, status=422)
    external_role = str(payload.get('role') or '')
    with transaction.atomic():
        lead = Lead.objects.select_for_update().filter(pk=lead_id, is_archived=False).first()
        if lead is None:
            return JsonResponse({'detail': 'Lead not found.'}, status=404)
        if not lead.manager_id:
            return JsonResponse({'detail': 'Lead must be claimed first.'}, status=409)
        allowed = lead.manager_id == actor.id or actor.is_staff or actor.is_superuser or external_role in LEADERSHIP_ROLES
        if not allowed:
            return JsonResponse({'detail': 'Only the assigned manager or leadership may process this lead.'}, status=403)
        if not lead.processed_at:
            lead.status = 'contacted'
            lead.processed_at = timezone.now()
            lead.processed_by = actor
            lead.log_action('processed_from_elite_task', actor)
            lead.save(update_fields=['status', 'processed_at', 'processed_by', 'custom_data', 'updated_at'])
    return JsonResponse({'ok': True, 'lead_id': lead.pk, 'status': lead.status})


@shared_task(name='crm.send_weekly_lead_report')
def send_weekly_lead_report():
    now = timezone.now()
    local_day = timezone.localdate(now)
    start_day = local_day - timedelta(days=local_day.weekday())
    start = timezone.make_aware(datetime.combine(start_day, time.min))
    leads = Lead.objects.filter(api_source='website', created_at__gte=start, created_at__lte=now)
    total = leads.count()
    claimed = leads.filter(manager__isnull=False).count()
    processed = leads.filter(processed_at__isnull=False).count()
    average = leads.filter(taken_at__isnull=False).aggregate(
        value=Avg(F('taken_at') - F('created_at'))
    )['value']
    manager_rows = (
        leads.filter(manager__isnull=False)
        .values('manager__first_name', 'manager__last_name', 'manager__email')
        .annotate(total=Count('id'), processed=Count('id', filter=Q(processed_at__isnull=False)))
        .order_by('-processed', '-total')
    )
    managers = []
    for row in manager_rows:
        name = f"{row['manager__first_name']} {row['manager__last_name']}".strip() or row['manager__email']
        managers.append(f"• {name}: {row['processed']} из {row['total']}")
    return _elite_task_post(
        '/integrations/v1/crm/reports',
        {
            'period_label': f'{start_day:%d.%m}–{local_day:%d.%m.%Y}',
            'total': total,
            'claimed': claimed,
            'processed': processed,
            'unprocessed': max(total - processed, 0),
            'average_claim_minutes': round(average.total_seconds() / 60) if average else None,
            'managers': managers,
        },
    )
