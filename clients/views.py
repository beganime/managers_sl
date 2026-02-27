# clients/views.py
from rest_framework import viewsets, permissions
from django.db.models import Q
from .models import Client
from .serializers import ClientSerializer
from django.utils.dateparse import parse_datetime

class ClientViewSet(viewsets.ModelViewSet):
    """
    REST API для работы с клиентами из мобильного приложения.
    Обеспечивает изоляцию данных (менеджер видит только своих).
    """
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # 1. Фильтрация по правам (по аналогии с твоим admin.py)
        if user.is_superuser:
            qs = Client.objects.all()
        else:
            qs = Client.objects.filter(Q(manager=user) | Q(shared_with=user)).distinct()
            
        # 2. Логика для OFFLINE SYNC (Pull)
        # Приложение RN передает ?updated_after=2026-02-27T10:00:00Z
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        # При создании нового клиента через приложение жестко привязываем его к текущему менеджеру
        serializer.save(manager=self.request.user)