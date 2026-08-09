# leads/views.py
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.crm.models import (
    Client as CrmClient,
    ClientFile as CrmClientFile,
    ClientQuestionnaire as CrmClientQuestionnaire,
    Lead as CrmLead,
    LeadSource as CrmLeadSource,
)
from apps.organizations.models import Company
from apps.sheets_sync.models import ClientAdmissionSnapshot

from .models import Lead
from .serializers import LeadSerializer, MobileLeadSerializer

User = get_user_model()


def clean_header(value, max_length=None) -> str:
    value = str(value or '').strip()

    if max_length and len(value) > max_length:
        return value[:max_length]

    return value


def get_client_ip(request) -> str | None:
    """
    Берём реальный IP без изменения frontend/mobile.
    Работает за nginx/proxy, если он передаёт X-Forwarded-For или X-Real-IP.
    """
    cloudflare_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cloudflare_ip:
        return clean_header(cloudflare_ip, 45)

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        first_ip = x_forwarded_for.split(',')[0].strip()
        if first_ip:
            return clean_header(first_ip, 45)

    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        return clean_header(x_real_ip, 45)

    remote_addr = request.META.get('REMOTE_ADDR')
    if remote_addr:
        return clean_header(remote_addr, 45)

    return None


class IsAuthorizedAPIClient(BasePermission):
    """Разрешает доступ для создания лидов с сайта по API-ключу."""

    def has_permission(self, request, view):
        provided_key = request.headers.get('X-API-KEY')
        actual_key = getattr(settings, 'LEADS_API_KEY', None)
        return provided_key == actual_key


class LeadCreateThrottle(AnonRateThrottle):
    """
    Ограничение по IP: максимум 3 заявки в минуту.
    IP берётся из proxy headers, чтобы боты не обходили лимит через nginx.
    """
    rate = '3/min'
    scope = 'leads_create'

    def get_ident(self, request):
        return get_client_ip(request) or super().get_ident(request)


CRM_LEAD_FIELD_MAP = {
    'ФИО студента': 'student_name',
    'Наличие паспорта': 'has_passport',
    'Месяц поездки': 'travel_month',
    'Город вылета': 'departure_city',
    'Дата поездки': 'travel_date',
    'Город прибытия': 'arrival_city',
    'Багаж': 'luggage',
    'Текущее образование': 'current_education',
    'Текущий университет': 'current_university',
    'Текущая страна': 'current_country',
}


def default_crm_lead_company():
    configured_id = getattr(settings, 'LEADS_DEFAULT_COMPANY_ID', None)
    qs = Company.objects.all().order_by('id')
    if configured_id:
        company = qs.filter(pk=configured_id).first()
        if company:
            return company
    return qs.first()


def default_crm_manager():
    return User.objects.filter(is_active=True, is_staff=True).order_by('id').first() or User.objects.filter(is_active=True).order_by('id').first()


def find_mobile_client(data):
    mobile_user_id = data.get('mobile_user_id') or data.get('user_id')
    email = clean_header(data.get('email'), 255)
    phone = clean_header(data.get('phone') or data.get('whatsapp'), 50)
    qs = CrmClient.objects.all()
    if mobile_user_id:
        client = qs.filter(mobile_app_user_id=mobile_user_id).first()
        if client:
            return client
    if email:
        client = qs.filter(email__iexact=email).first()
        if client:
            return client
    if phone:
        client = qs.filter(phone=phone).first()
        if client:
            return client
    return None


def upsert_mobile_client(data):
    company = default_crm_lead_company()
    manager = default_crm_manager()
    if not company or not manager:
        raise ValueError('No company or manager exists for mobile client sync.')

    mobile_user_id = data.get('mobile_user_id') or data.get('user_id')
    profile = data.get('profile') or {}
    full_name = clean_header(
        data.get('full_name')
        or ' '.join(part for part in [data.get('first_name'), data.get('last_name')] if part)
        or data.get('username')
        or data.get('email')
        or 'Mobile client',
        255,
    )
    phone = clean_header(data.get('phone') or profile.get('phone') or profile.get('whatsapp') or '', 50)
    email = clean_header(data.get('email'), 255) or None
    client = find_mobile_client({'mobile_user_id': mobile_user_id, 'email': email, 'phone': phone})
    created = False
    if not client:
        client = CrmClient(company=company, manager=manager, full_name=full_name, phone=phone or '-', email=email)
        created = True

    client.company = client.company or company
    client.manager = client.manager or manager
    client.full_name = full_name or client.full_name
    client.phone = phone or client.phone
    client.email = email or client.email
    client.citizenship = clean_header(profile.get('citizenship') or data.get('citizenship'), 100)
    client.city = clean_header(profile.get('city') or data.get('city'), 100)
    client.mobile_app_user_id = mobile_user_id or client.mobile_app_user_id
    client.mobile_app_source = True
    custom_data = dict(client.custom_data or {})
    custom_data['mobile_app_profile'] = data
    client.custom_data = custom_data
    client.save()
    current_location = clean_header(
        profile.get('current_location') or data.get('current_location'),
        255,
    )
    if current_location:
        snapshot, _ = ClientAdmissionSnapshot.objects.get_or_create(client=client)
        snapshot.current_location = current_location
        snapshot.last_imported_at = timezone.now()
        snapshot.save(update_fields=['current_location', 'last_imported_at', 'updated_at'])
        submission = getattr(client, 'onboarding_submission', None)
        if submission:
            from apps.sheets_sync.services import enqueue_submission_sync
            enqueue_submission_sync(submission.pk)
    return client, created


class MobileClientSyncAPIView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        actual_key = getattr(settings, 'LEADS_API_KEY', '')
        if not actual_key or request.headers.get('X-API-KEY') != actual_key:
            return Response({'detail': 'Invalid API key.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            client, created = upsert_mobile_client(request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'id': client.id, 'created': created, 'detail': 'Client synced.'}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class MobileClientDocumentSyncAPIView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        actual_key = getattr(settings, 'LEADS_API_KEY', '')
        if not actual_key or request.headers.get('X-API-KEY') != actual_key:
            return Response({'detail': 'Invalid API key.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            client, _ = upsert_mobile_client(request.data.get('client') or request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        mobile_document_id = request.data.get('mobile_document_id') or request.data.get('document_id')
        if not mobile_document_id:
            return Response({'detail': 'mobile_document_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        document_status = request.data.get('status') or CrmClientFile.STATUS_PENDING
        if document_status not in {CrmClientFile.STATUS_PENDING, CrmClientFile.STATUS_APPROVED, CrmClientFile.STATUS_REJECTED}:
            return Response({'status': 'Invalid document status.'}, status=status.HTTP_400_BAD_REQUEST)
        reviewed_at = timezone.now() if document_status in {CrmClientFile.STATUS_APPROVED, CrmClientFile.STATUS_REJECTED} else None
        document, _ = CrmClientFile.objects.update_or_create(
            external_mobile_document_id=mobile_document_id,
            defaults={
                'client': client,
                'title': clean_header(request.data.get('title'), 255) or 'Mobile document',
                'file': '',
                'file_type': clean_header(request.data.get('file_type') or 'mobile_document', 100),
                'external_file_url': clean_header(request.data.get('file_url') or request.data.get('file'), 1000),
                'external_mobile_user_id': request.data.get('mobile_user_id') or getattr(client, 'mobile_app_user_id', None),
                'source': 'students_life_mobile_app',
                'status': document_status,
                'review_comment': request.data.get('admin_comment') or '',
                'reviewed_at': reviewed_at,
                'comment': request.data.get('description') or '',
            },
        )
        return Response({'id': document.id, 'client_id': client.id, 'detail': 'Document synced.'})


class MobileClientQuestionnaireSyncAPIView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        actual_key = getattr(settings, 'LEADS_API_KEY', '')
        if not actual_key or request.headers.get('X-API-KEY') != actual_key:
            return Response({'detail': 'Invalid API key.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            client, _ = upsert_mobile_client(request.data.get('client') or request.data)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        mobile_questionnaire_id = request.data.get('mobile_questionnaire_id') or request.data.get('questionnaire_id')
        submitted_at = parse_datetime(request.data.get('submitted_at') or '')
        data = dict(request.data)
        questionnaire_status = request.data.get('status') or CrmClientQuestionnaire.STATUS_COMPLETED
        if questionnaire_status not in {
            CrmClientQuestionnaire.STATUS_DRAFT,
            CrmClientQuestionnaire.STATUS_COMPLETED,
            CrmClientQuestionnaire.STATUS_SUBMITTED,
            CrmClientQuestionnaire.STATUS_APPROVED,
            CrmClientQuestionnaire.STATUS_REJECTED,
            CrmClientQuestionnaire.STATUS_UPDATED,
        }:
            questionnaire_status = CrmClientQuestionnaire.STATUS_COMPLETED
        questionnaire, _ = CrmClientQuestionnaire.objects.update_or_create(
            client=client,
            defaults={
                'mobile_questionnaire_id': mobile_questionnaire_id or None,
                'external_mobile_user_id': request.data.get('mobile_user_id') or getattr(client, 'mobile_app_user_id', None),
                'source': request.data.get('source') or 'students_life_mobile_app',
                'status': questionnaire_status,
                'full_name': clean_header(request.data.get('full_name') or client.full_name, 255),
                'phone': clean_header(request.data.get('phone') or client.phone, 80),
                'email': clean_header(request.data.get('email') or client.email, 255) or None,
                'citizenship': clean_header(request.data.get('citizenship'), 120),
                'desired_program': clean_header(request.data.get('desired_program'), 255),
                'desired_country': clean_header(request.data.get('desired_country'), 120),
                'desired_city': clean_header(request.data.get('desired_city'), 120),
                'face_photo_url': clean_header(request.data.get('face_photo_url'), 1000),
                'data': data,
                'submitted_at': submitted_at,
                'last_synced_at': timezone.now(),
            },
        )
        generated_url = request.data.get('generated_document_url') or request.data.get('document_file') or ''
        return Response({
            'id': questionnaire.id,
            'client_id': client.id,
            'generated_document_url': generated_url,
            'detail': 'Questionnaire synced.',
        })


def normalize_crm_lead_payload(data):
    payload = data.copy() if hasattr(data, 'copy') else dict(data or {})
    custom_data = {}
    for source_key, target_key in CRM_LEAD_FIELD_MAP.items():
        if source_key in payload:
            custom_data[target_key] = payload.get(source_key)

    full_name = (
        payload.get('full_name')
        or payload.get('name')
        or payload.get('ФИО студента')
        or payload.get('student_name')
        or payload.get('ФИО')
        or 'Новая заявка'
    )
    phone = payload.get('phone') or payload.get('Телефон') or payload.get('telephone') or ''
    email = payload.get('email') or payload.get('Email') or ''
    direction = payload.get('direction') or payload.get('Направление') or ''
    allowed_directions = {choice[0] for choice in CrmLead.DIRECTION_CHOICES}
    if direction not in allowed_directions:
        custom_data['raw_direction'] = direction
        direction = 'other' if direction else ''

    known_keys = {
        'full_name',
        'name',
        'phone',
        'telephone',
        'email',
        'Email',
        'country',
        'city',
        'direction',
        'interested_country',
        'interested_program',
        'comment',
        'message',
        'Направление',
        'Телефон',
        'ФИО',
    } | set(CRM_LEAD_FIELD_MAP.keys())

    for key, value in payload.items():
        if key not in known_keys:
            custom_data[key] = value

    return {
        'full_name': clean_header(full_name, 255) or 'Новая заявка',
        'phone': clean_header(phone, 50),
        'email': clean_header(email, 255) or None,
        'country': clean_header(payload.get('country') or payload.get('Страна'), 100),
        'city': clean_header(payload.get('city') or payload.get('Город'), 100),
        'direction': direction,
        'interested_country': clean_header(payload.get('interested_country') or payload.get('Интересующая страна'), 100),
        'interested_program': clean_header(payload.get('interested_program') or payload.get('Интересующая программа'), 255),
        'comment': payload.get('comment') or payload.get('message') or '',
        'custom_data': {'raw_payload': dict(payload), **custom_data},
    }


class LeadCreateAPIView(APIView):
    permission_classes = []
    throttle_classes = [LeadCreateThrottle]

    def post(self, request, *args, **kwargs):
        actual_key = getattr(settings, 'LEADS_API_KEY', '')
        if not actual_key:
            return Response({'detail': 'LEADS_API_KEY is not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if request.headers.get('X-API-KEY') != actual_key:
            return Response({'detail': 'Invalid API key.'}, status=status.HTTP_403_FORBIDDEN)

        company = default_crm_lead_company()
        if not company:
            return Response({'detail': 'No company exists for incoming leads.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        source, _ = CrmLeadSource.objects.get_or_create(
            code='website',
            defaults={'name': 'Website', 'description': 'Incoming leads from external website'},
        )
        data = normalize_crm_lead_payload(request.data)
        if not data['phone'] and not data['email']:
            return Response({'detail': 'Phone or email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        lead = CrmLead.objects.create(
            company=company,
            source=source,
            status='new',
            submitter_ip=get_client_ip(request),
            submitter_user_agent=clean_header(request.META.get('HTTP_USER_AGENT'), 2000),
            submitter_referer=clean_header(request.META.get('HTTP_REFERER'), 1000),
            submitter_origin=clean_header(request.META.get('HTTP_ORIGIN'), 1000),
            api_source='website',
            **data,
        )
        lead.log_action('created_from_website', note='Создано через /api/leads/create/', save=True)

        try:
            from notifications.firebase import notify_admins_about_new_lead
            notify_admins_about_new_lead(lead)
        except Exception:
            pass

        return Response(
            {
                'id': lead.id,
                'status': lead.status,
                'detail': 'Lead created.',
            },
            status=status.HTTP_201_CREATED,
        )

class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = MobileLeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _is_admin(self, user):
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or user.is_staff
                or getattr(user, 'role', None) == 'admin'
            )
        )

    def get_queryset(self):
        user = self.request.user
        is_admin = self._is_admin(user)

        qs = Lead.objects.select_related('manager').all()

        if not is_admin:
            qs = qs.filter(Q(manager=user) | Q(manager__isnull=True)).distinct()

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        direction = self.request.query_params.get('direction')
        if direction:
            qs = qs.filter(direction=direction)

        manager_id = self.request.query_params.get('manager')
        if manager_id and is_admin:
            qs = qs.filter(manager_id=manager_id)

        unassigned = self.request.query_params.get('unassigned')
        if unassigned in ('1', 'true'):
            qs = qs.filter(manager__isnull=True)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(full_name__icontains=search)
                | Q(student_name__icontains=search)
                | Q(parent_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
                | Q(country__icontains=search)
                | Q(departure_city__icontains=search)
                | Q(arrival_city__icontains=search)
                | Q(submitter_ip__icontains=search)
                | Q(submitter_user_agent__icontains=search)
                | Q(submitter_origin__icontains=search)
                | Q(submitter_host__icontains=search)
            )

        ordering = self.request.query_params.get('ordering') or '-created_at'

        allowed = {
            'created_at',
            '-created_at',
            'updated_at',
            '-updated_at',
            'full_name',
            '-full_name',
            'status',
            '-status',
            'direction',
            '-direction',
        }

        if ordering not in allowed:
            ordering = '-created_at'

        return qs.distinct().order_by(ordering)

    def perform_update(self, serializer):
        instance = self.get_object()
        status_value = serializer.validated_data.get('status')

        if not instance.manager and status_value == 'contacted':
            serializer.save(manager=self.request.user)
            return

        serializer.save()

    @action(detail=True, methods=['post'], url_path='take')
    def take(self, request, pk=None):
        lead = self.get_object()

        if lead.manager and lead.manager_id != request.user.id:
            return Response(
                {'detail': 'Заявка уже закреплена за другим менеджером.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lead.manager = request.user
        lead.status = 'contacted'
        lead.save(update_fields=['manager', 'status', 'updated_at'])

        return Response(self.get_serializer(lead).data, status=status.HTTP_200_OK)
