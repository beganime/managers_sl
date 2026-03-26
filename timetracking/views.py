# timetracking/views.py
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import WorkShift
from .serializers import WorkShiftSerializer


class WorkShiftViewSet(viewsets.ModelViewSet):
    """
    REST API для рабочих смен.
    Админ видит все смены.
    Менеджер видит только свои.
    """
    serializer_class = WorkShiftSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        is_admin = user.is_superuser or getattr(user, 'role', None) == 'admin'

        qs = (
            WorkShift.objects.select_related('employee').all()
            if is_admin
            else WorkShift.objects.select_related('employee').filter(employee=user)
        )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        employee_id = self.request.query_params.get('employee')
        if employee_id and is_admin:
            qs = qs.filter(employee_id=employee_id)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)

        return qs.order_by('-date', '-time_in', '-id')

    def perform_create(self, serializer):
        user = self.request.user
        today = timezone.localdate()

        if WorkShift.objects.filter(employee=user, date=today, is_active=True).exists():
            raise ValidationError({"detail": "У вас уже есть активная смена на сегодня."})

        serializer.save(employee=user)

    @action(detail=False, methods=['get'], url_path='current')
    def current_shift(self, request):
        user = request.user
        shift = WorkShift.objects.filter(employee=user, is_active=True).order_by('-time_in').first()

        if not shift:
            return Response({"detail": "Нет активной смены"}, status=status.HTTP_404_NOT_FOUND)

        return Response(self.get_serializer(shift).data)

    @action(detail=False, methods=['post'], url_path='start_day')
    def start_day(self, request):
        user = request.user
        today = timezone.localdate()

        active_shift = WorkShift.objects.filter(employee=user, is_active=True).order_by('-time_in').first()
        if active_shift:
            return Response(
                {
                    "detail": "Рабочий день уже начат.",
                    "shift": self.get_serializer(active_shift).data
                },
                status=status.HTTP_200_OK
            )

        shift = WorkShift.objects.create(
            employee=user,
            date=today,
            time_in=timezone.now(),
            is_active=True,
        )

        return Response(
            {
                "detail": "Рабочий день успешно начат.",
                "shift": self.get_serializer(shift).data
            },
            status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=['post'], url_path='end_day')
    def end_day(self, request):
        user = request.user
        shift = WorkShift.objects.filter(employee=user, is_active=True).order_by('-time_in').first()

        if not shift:
            return Response(
                {"detail": "Нет активной смены для завершения."},
                status=status.HTTP_400_BAD_REQUEST
            )

        shift.time_out = timezone.now()
        shift.is_active = False
        shift.save()

        return Response(
            {
                "detail": "Рабочий день завершён.",
                "shift": self.get_serializer(shift).data
            },
            status=status.HTTP_200_OK
        )