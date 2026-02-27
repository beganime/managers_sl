from rest_framework.generics import CreateAPIView
from rest_framework.permissions import BasePermission
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from django.conf import settings
from .models import Lead
from .serializers import LeadSerializer, MobileLeadSerializer

# Создаем кастомную защиту
class IsAuthorizedAPIClient(BasePermission):
    """
    Разрешает доступ только если передан правильный X-API-KEY в заголовках.
    """
    def has_permission(self, request, view):
        # Достаем ключ из заголовков запроса
        provided_key = request.headers.get('X-API-KEY')
        # Сравниваем с ключом из настроек
        actual_key = getattr(settings, 'LEADS_API_KEY', None)
        
        # Если совпадают - пускаем, если нет - выдаст 403 Forbidden
        return provided_key == actual_key

# Твоя вьюшка
class LeadCreateAPIView(CreateAPIView):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    # Применяем нашу защиту вместо AllowAny
    permission_classes = [IsAuthorizedAPIClient]


# --- АПИ ДЛЯ МОБИЛЬНОГО ПРИЛОЖЕНИЯ (SYNC) ---
class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = MobileLeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if user.is_superuser:
            qs = Lead.objects.all()
        else:
            # Менеджер видит: Свои заявки ИЛИ Новые ничьи заявки
            qs = Lead.objects.filter(Q(manager=user) | Q(manager__isnull=True)).distinct()
            
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')