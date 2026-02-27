# reports/views.py
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from .models import DailyReport
from .serializers import DailyReportSerializer

class DailyReportViewSet(viewsets.ModelViewSet):
    """
    REST API для ежедневных отчетов.
    """
    serializer_class = DailyReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = DailyReport.objects.all() if user.is_superuser else DailyReport.objects.filter(employee=user)
            
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(employee=self.request.user)