# users/views.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime
from .models import User, Office
from .serializers import UserSerializer, OfficeSerializer

class OfficeViewSet(viewsets.ReadOnlyModelViewSet):
    """API для получения списка офисов (Только чтение)"""
    serializer_class = OfficeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Office.objects.all()
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API для:
    1. Получения списка активных сотрудников (коллег) для связи и задач (Только чтение).
    2. Получения и редактирования собственного профиля (через /users/me/).
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Отдаем только активных сотрудников
        qs = User.objects.filter(is_active=True)
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')

    @action(detail=False, methods=['get', 'patch'], url_path='me')
    def my_profile(self, request):
        """
        Эндпоинт для текущего пользователя:
        GET /api/users/users/me/ - получить свой профиль
        PATCH /api/users/users/me/ - обновить свои данные (имя, аватар, соцсети)
        """
        user = request.user
        
        if request.method == 'GET':
            serializer = self.get_serializer(user)
            return Response(serializer.data)
            
        elif request.method == 'PATCH':
            # partial=True означает, что можно передать не все поля, а только измененные
            serializer = self.get_serializer(user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)