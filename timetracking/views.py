# timetracking/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from .models import WorkShift
from .serializers import WorkShiftSerializer

class WorkShiftViewSet(viewsets.ModelViewSet):
    """
    REST API для рабочих смен.
    Менеджер видит и управляет только своими сменами.
    """
    serializer_class = WorkShiftSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = WorkShift.objects.all() if user.is_superuser else WorkShift.objects.filter(employee=user)
            
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        user = self.request.user
        today = timezone.now().date()
        
        # Проверка: не даем начать вторую смену, если первая еще активна
        if WorkShift.objects.filter(employee=user, date=today, is_active=True).exists():
            raise ValidationError({"detail": "У вас уже есть активная смена на сегодня!"})
            
        serializer.save(employee=user)

    # --- НОВЫЙ ЭНДПОИНТ ДЛЯ ФРОНТЕНДА ---
    # Обрабатывает GET и PATCH запросы по адресу /api/timetracking/shifts/current/
    @action(detail=False, methods=['patch', 'get'], url_path='current')
    def current_shift(self, request):
        shift = self.get_queryset().filter(is_active=True).first()
        if not shift:
            return Response({"detail": "Нет активной смены"}, status=status.HTTP_404_NOT_FOUND)
        
        if request.method == 'PATCH':
            shift.time_out = timezone.now()
            shift.is_active = False # Модель сама посчитает часы при сохранении
            shift.save()
            return Response(self.get_serializer(shift).data)
        
        return Response(self.get_serializer(shift).data)