# gamification/views.py
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from .models import Notification, Leaderboard
from .serializers import NotificationSerializer, LeaderboardSerializer

class NotificationViewSet(viewsets.ModelViewSet):
    """
    API для уведомлений. 
    Менеджер видит только свои уведомления.
    Может отмечать их как прочитанные (PATCH).
    """
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

        # Сортируем: новые сверху
        return qs.order_by('-created_at')

class LeaderboardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API для текущего рейтинга (Топ менеджеров). 
    Только для чтения.
    """
    serializer_class = LeaderboardSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Отдаем только тех, у кого есть профиль зарплаты (менеджеров)
        # Сортировка уже задана в прокси-модели Leaderboard (по выручке)
        return Leaderboard.objects.filter(managersalary__isnull=False)