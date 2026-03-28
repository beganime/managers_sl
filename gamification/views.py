# gamification/views.py
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets

from .models import Notification, Leaderboard
from .serializers import NotificationSerializer, LeaderboardSerializer


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