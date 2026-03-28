# gamification/views.py
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Notification, Leaderboard, TutorialVideo
from .serializers import (
    NotificationSerializer,
    LeaderboardSerializer,
    TutorialVideoSerializer,
)


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or user.is_staff or getattr(user, 'role', None) == 'admin'
        )
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


class TutorialVideoViewSet(viewsets.ModelViewSet):
    serializer_class = TutorialVideoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = TutorialVideo.objects.all()

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может добавлять видео.')
        serializer.save()

    def perform_update(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может изменять видео.')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может удалять видео.')
        instance.delete()


class LeaderboardViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LeaderboardSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Leaderboard.objects
            .select_related('managersalary', 'office')
            .filter(managersalary__isnull=False)
            .order_by('-managersalary__current_month_revenue', 'first_name', 'last_name', 'id')
        )