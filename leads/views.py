# leads/views.py
from django.conf import settings
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import Lead
from .serializers import LeadSerializer, MobileLeadSerializer


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


class LeadCreateAPIView(CreateAPIView):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthorizedAPIClient]
    throttle_classes = [LeadCreateThrottle]

    def perform_create(self, serializer):
        request = self.request

        lead = serializer.save(
            submitter_ip=get_client_ip(request),
            submitter_user_agent=clean_header(request.META.get('HTTP_USER_AGENT'), 2000),
            submitter_referer=clean_header(request.META.get('HTTP_REFERER'), 1000),
            submitter_origin=clean_header(request.META.get('HTTP_ORIGIN'), 255),
            submitter_host=clean_header(request.META.get('HTTP_HOST'), 255),
        )

        try:
            from notifications.firebase import notify_admins_about_new_lead
            notify_admins_about_new_lead(lead)
        except Exception:
            pass

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