from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from analytics.models import FinancialPeriod
from users.permissions import is_admin_user

from .firebase_service import send_push_to_tokens
from .models import Leaderboard, Notification
from .push_models import DeviceToken, PushBroadcast
from .serializers import (
    DeviceTokenSerializer,
    LeaderboardSerializer,
    NotificationSerializer,
    PushBroadcastSerializer,
)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Notification.objects.filter(recipient=user)

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.order_by('-created_at')


class DeviceTokenViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceTokenSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user).order_by('-last_seen_at')

    def create(self, request, *args, **kwargs):
        token = request.data.get('token')
        if not token:
            return Response({'detail': 'token обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        instance, _ = DeviceToken.objects.update_or_create(
            token=token,
            defaults={
                'user': request.user,
                'platform': request.data.get('platform', 'unknown'),
                'device_name': request.data.get('device_name', ''),
                'is_active': True,
            },
        )

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='deactivate')
    def deactivate(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'detail': 'token обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        DeviceToken.objects.filter(user=request.user, token=token).update(is_active=False)
        return Response({'detail': 'Токен деактивирован'})


class PushBroadcastViewSet(viewsets.ModelViewSet):
    serializer_class = PushBroadcastSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not is_admin_user(self.request.user):
            return PushBroadcast.objects.none()

        return PushBroadcast.objects.all()

    def create(self, request, *args, **kwargs):
        if not is_admin_user(request.user):
            return Response(
                {'detail': 'Только админ может делать рассылку'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        broadcast = serializer.save(created_by=request.user)

        return Response(self.get_serializer(broadcast).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='send')
    def send(self, request, pk=None):
        if not is_admin_user(request.user):
            return Response(
                {'detail': 'Только админ может делать рассылку'},
                status=status.HTTP_403_FORBIDDEN,
            )

        broadcast = self.get_object()
        tokens_qs = DeviceToken.objects.filter(is_active=True)

        user_ids = request.data.get('user_ids') or []
        if user_ids:
            tokens_qs = tokens_qs.filter(user_id__in=user_ids)

        tokens = list(tokens_qs.values_list('token', flat=True).distinct())

        result = send_push_to_tokens(
            tokens=tokens,
            title=broadcast.title,
            body=broadcast.body,
        )

        broadcast.sent_count = result.get('success_count', 0)
        broadcast.failed_count = result.get('failure_count', 0)
        broadcast.sent_at = timezone.now()
        broadcast.save(update_fields=['sent_count', 'failed_count', 'sent_at'])

        recipients = tokens_qs.values_list('user_id', flat=True).distinct()
        notifications = [
            Notification(
                recipient_id=user_id,
                title=broadcast.title,
                body=broadcast.body,
            )
            for user_id in recipients
        ]

        if notifications:
            Notification.objects.bulk_create(notifications)

        return Response(
            {
                'detail': 'Рассылка выполнена',
                'broadcast': self.get_serializer(broadcast).data,
                'firebase': result,
            }
        )


class LeaderboardViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LeaderboardSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _period_dates(self):
        params = self.request.query_params

        if params.get('current_period') in ('1', 'true', 'True'):
            period = FinancialPeriod.ensure_current_period()
            return period.start_date, period.end_date

        date_from = parse_date(params.get('date_from') or '')
        date_to = parse_date(params.get('date_to') or '')

        today = timezone.localdate()

        if not date_to:
            date_to = today

        if not date_from:
            date_from = date_to.replace(day=1)

        return date_from, date_to

    def get_serializer_context(self):
        context = super().get_serializer_context()
        date_from, date_to = self._period_dates()

        context['kpi_date_from'] = date_from
        context['kpi_date_to'] = date_to
        context['rank_map'] = getattr(self, '_rank_map', {})

        return context

    def get_queryset(self):
        user = self.request.user
        qs = (
            Leaderboard.objects
            .select_related(
                'office',
                'managersalary',
                'access_profile',
                'access_profile__managed_office',
            )
            .filter(is_active=True)
        )

        include_hidden = self.request.query_params.get('include_hidden') in ('1', 'true', 'True')
        if not include_hidden or not is_admin_user(user):
            qs = qs.filter(
                Q(access_profile__can_be_in_leaderboard=True)
                | Q(access_profile__isnull=True)
            )

        office_id = self.request.query_params.get('office')
        if office_id:
            qs = qs.filter(office_id=office_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(middle_name__icontains=search)
                | Q(email__icontains=search)
                | Q(office__city__icontains=search)
            )

        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)

        return qs.distinct().order_by('last_name', 'first_name', 'id')

    def list(self, request, *args, **kwargs):
        queryset = list(self.filter_queryset(self.get_queryset()))

        first_serializer = self.get_serializer(queryset, many=True)
        data = list(first_serializer.data)

        data.sort(
            key=lambda item: (
                float(item.get('total_score') or 0),
                float(item.get('revenue') or 0),
            ),
            reverse=True,
        )

        self._rank_map = {}

        for index, item in enumerate(data, start=1):
            item['rank'] = index
            user_id = item.get('id')
            if user_id is not None:
                self._rank_map[user_id] = index

        return Response(data)