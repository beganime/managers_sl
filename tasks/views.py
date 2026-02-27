# tasks/views.py
from rest_framework import viewsets, permissions
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from .models import Task
from .serializers import TaskSerializer

class TaskViewSet(viewsets.ModelViewSet):
    """
    REST API для задач.
    Менеджер видит задачи, которые назначены на него ИЛИ созданы им.
    """
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        if user.is_superuser:
            qs = Task.objects.all()
        else:
            qs = Task.objects.filter(Q(assigned_to=user) | Q(created_by=user)).distinct()
            
        # Оффлайн синхронизация (Pull)
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        # Автоматически ставим текущего менеджера как постановщика задачи
        serializer.save(created_by=self.request.user)