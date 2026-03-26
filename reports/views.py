# reports/views.py
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import DailyReport
from .serializers import DailyReportSerializer


class DailyReportViewSet(viewsets.ModelViewSet):
    serializer_class = DailyReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        is_admin = user.is_superuser or getattr(user, 'role', None) == 'admin'

        qs = (
            DailyReport.objects.select_related('employee').all()
            if is_admin
            else DailyReport.objects.select_related('employee').filter(employee=user)
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

        return qs.order_by('-date', '-id')

    def perform_create(self, serializer):
        serializer.save(employee=self.request.user)

    @action(detail=False, methods=['get'], url_path='today')
    def check_today(self, request):
        today = timezone.localdate()
        report = self.get_queryset().filter(date=today).first()

        if report:
            return Response(self.get_serializer(report).data)

        return Response({'detail': 'Отчёт за сегодня не найден'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'], url_path='submit_today')
    def submit_today(self, request):
        today = timezone.localdate()
        existing = DailyReport.objects.filter(employee=request.user, date=today).first()

        if existing:
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(
                {
                    'detail': 'Отчёт за сегодня обновлён.',
                    'report': serializer.data
                },
                status=status.HTTP_200_OK
            )

        payload = request.data.copy()
        payload['date'] = str(today)

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(employee=request.user)

        return Response(
            {
                'detail': 'Отчёт за сегодня создан.',
                'report': serializer.data
            },
            status=status.HTTP_201_CREATED
        )