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

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Создаем тот самый путь /api/users/users/me/
    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)