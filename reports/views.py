# reports/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from .models import DailyReport
from .serializers import DailyReportSerializer


class DailyReportViewSet(viewsets.ModelViewSet):
    serializer_class   = DailyReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Суперадмин видит все отчёты, менеджер — только свои
        qs = (
            DailyReport.objects.select_related('employee')
            if user.is_superuser
            else DailyReport.objects.filter(employee=user).select_related('employee')
        )
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-date')

    def perform_create(self, serializer):
        serializer.save(employee=self.request.user)

    @action(detail=False, methods=['get'], url_path='today')
    def check_today(self, request):
        today  = timezone.now().date()
        report = self.get_queryset().filter(date=today).first()
        if report:
            return Response(self.get_serializer(report).data)
        return Response({'detail': 'Отчёт не найден'}, status=status.HTTP_404_NOT_FOUND)