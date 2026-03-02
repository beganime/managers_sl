# leads/views.py
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import BasePermission
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from django.conf import settings
from django.db.models import Q
from .models import Lead
from .serializers import LeadSerializer, MobileLeadSerializer

class IsAuthorizedAPIClient(BasePermission):
    """Разрешает доступ для создания лидов с сайта по API-ключу."""
    def has_permission(self, request, view):
        provided_key = request.headers.get('X-API-KEY')
        actual_key = getattr(settings, 'LEADS_API_KEY', None)
        return provided_key == actual_key

class LeadCreateAPIView(CreateAPIView):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthorizedAPIClient]

# --- АПИ ДЛЯ МОБИЛЬНОГО ПРИЛОЖЕНИЯ ---
class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = MobileLeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if user.is_superuser:
            qs = Lead.objects.all()
        else:
            # Менеджер видит: Свои заявки ИЛИ Ничьи заявки (manager__isnull=True)
            qs = Lead.objects.filter(Q(manager=user) | Q(manager__isnull=True)).distinct()
            
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')

    def perform_update(self, serializer):
        # Если статус меняется на "contacted" (В работу) и менеджер пустой, забираем лид себе
        instance = self.get_object()
        if not instance.manager and serializer.validated_data.get('status') == 'contacted':
            serializer.save(manager=self.request.user)
        else:
            serializer.save()