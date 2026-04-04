from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.permissions import is_admin_user
from .firebase_service import send_push_to_tokens
from .models import Notification, Leaderboard
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
            return Response({'detail': 'Только админ может делать рассылку'}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        broadcast = serializer.save(created_by=request.user)
        return Response(self.get_serializer(broadcast).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='send')
    def send(self, request, pk=None):
        if not is_admin_user(request.user):
            return Response({'detail': 'Только админ может делать рассылку'}, status=status.HTTP_403_FORBIDDEN)

        broadcast = self.get_object()
        tokens_qs = DeviceToken.objects.filter(is_active=True)

        user_ids = request.data.get('user_ids') or []
        if user_ids:
            tokens_qs = tokens_qs.filter(user_id__in=user_ids)

        tokens = list(tokens_qs.values_list('token', flat=True).distinct())
        result = send_push_to_tokens(tokens=tokens, title=broadcast.title, body=broadcast.body)

        broadcast.sent_count = result.get('success_count', 0)
        broadcast.failed_count = result.get('failure_count', 0)
        broadcast.sent_at = timezone.now()
        broadcast.save(update_fields=['sent_count', 'failed_count', 'sent_at'])

        # Локальные уведомления в БД
        recipients = tokens_qs.values_list('user_id', flat=True).distinct()
        notifications = [
            Notification(recipient_id=user_id, title=broadcast.title, body=broadcast.body)
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

    def get_queryset(self):
        qs = (
            Leaderboard.objects
            .select_related('managersalary', 'office', 'access_profile')
            .filter(managersalary__isnull=False)
            .filter(Q(access_profile__can_be_in_leaderboard=True) | Q(access_profile__isnull=True))
            .order_by('-managersalary__current_month_revenue', 'last_name', 'first_name')
        )
        office_id = self.request.query_params.get('office')
        if office_id:
            qs = qs.filter(office_id=office_id)
        return qs