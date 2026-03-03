# users/views.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import User, Office
from .serializers import UserSerializer, OfficeSerializer

class OfficeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Office.objects.all()
    serializer_class = OfficeSerializer
    permission_classes = [permissions.IsAuthenticated]

class UserViewSet(viewsets.ModelViewSet): # ИСПРАВЛЕНИЕ: Заменили ReadOnlyModelViewSet на ModelViewSet
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    # ИСПРАВЛЕНИЕ: Добавили 'patch' в methods
    @action(detail=False, methods=['get', 'patch'], url_path='me')
    def me(self, request):
        if request.method == 'PATCH':
            # partial=True позволяет обновлять только те поля, которые прислал фронтенд
            serializer = self.get_serializer(request.user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
            
        # Для GET-запроса
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)