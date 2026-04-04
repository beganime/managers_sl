from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.permissions import is_admin_user
from .ai_summary import build_admin_ai_summary
from .models import DailyReport
from .serializers import DailyReportSerializer


class DailyReportViewSet(viewsets.ModelViewSet):
    serializer_class = DailyReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DailyReport.objects.select_related('employee', 'employee__office').all()
        user = self.request.user

        if not is_admin_user(user):
            qs = qs.filter(employee=user)

        employee_id = self.request.query_params.get('employee')
        if employee_id:
            qs = qs.filter(employee_id=employee_id)

        office_id = self.request.query_params.get('office')
        if office_id:
            qs = qs.filter(employee__office_id=office_id)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            dt = parse_date(date_from)
            if dt:
                qs = qs.filter(date__gte=dt)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            dt = parse_date(date_to)
            if dt:
                qs = qs.filter(date__lte=dt)

        return qs.order_by('-date', '-created_at')

    def perform_create(self, serializer):
        serializer.save(employee=self.request.user)

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        report = DailyReport.objects.filter(
            employee=request.user,
            date=timezone.localdate(),
        ).first()
        if not report:
            return Response(None)
        return Response(self.get_serializer(report).data)

    @action(detail=False, methods=['post'], url_path='submit_today')
    def submit_today(self, request):
        report = DailyReport.objects.filter(
            employee=request.user,
            date=timezone.localdate(),
        ).first()

        serializer = self.get_serializer(
            report,
            data=request.data,
            partial=bool(report),
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(employee=request.user, date=timezone.localdate())
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='ai_summary')
    def ai_summary(self, request):
        if not is_admin_user(request.user):
            return Response({'detail': 'Только админ может смотреть итоговый AI отчёт'}, status=403)

        date_from = parse_date(request.query_params.get('date_from', '')) if request.query_params.get('date_from') else None
        date_to = parse_date(request.query_params.get('date_to', '')) if request.query_params.get('date_to') else None
        office_id = request.query_params.get('office')

        data = build_admin_ai_summary(date_from=date_from, date_to=date_to, office_id=office_id)
        return Response(data)