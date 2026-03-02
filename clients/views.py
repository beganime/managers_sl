# clients/views.py
from rest_framework import viewsets, permissions
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from .models import Client
from .serializers import ClientSerializer

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # Суперпользователь видит всю базу
        if user.is_superuser:
            qs = Client.objects.all()
        else:
            # Менеджер видит СВОИХ клиентов И тех, кто расшарен с ним
            qs = Client.objects.filter(Q(manager=user) | Q(shared_with=user)).distinct()
            
        # Логика для оффлайн синхронизации
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        # Жестко привязываем создателя как главного менеджера клиента
        serializer.save(manager=self.request.user)