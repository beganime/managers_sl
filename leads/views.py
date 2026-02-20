from rest_framework.generics import CreateAPIView
from rest_framework.permissions import BasePermission
from django.conf import settings
from .models import Lead
from .serializers import LeadSerializer

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