from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
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

    def _is_admin(self, user):
        return bool(
            user and (
                user.is_superuser
                or user.is_staff
                or getattr(user, 'role', None) == 'admin'
            )
        )

    def get_queryset(self):
        user = self.request.user
        is_admin = self._is_admin(user)

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

    def _get_open_shift(self, user):
        shift = (
            WorkShift.objects
            .filter(employee=user, is_active=True)
            .order_by('-date', '-time_in', '-id')
            .first()
        )
        if shift:
            return shift

        shift = (
            WorkShift.objects
            .filter(employee=user, time_out__isnull=True)
            .order_by('-date', '-time_in', '-id')
            .first()
        )
        return shift

    def perform_create(self, serializer):
        user = self.request.user
        open_shift = self._get_open_shift(user)

        if open_shift:
            raise ValidationError({"detail": "У вас уже есть незавершённая смена."})

        serializer.save(employee=user)

    @action(detail=False, methods=['get'], url_path='current')
    def current_shift(self, request):
        user = request.user
        shift = self._get_open_shift(user)

        if not shift:
            return Response(
                {
                    "is_active": False,
                    "shift": None,
                    "detail": "Активная смена отсутствует."
                },
                status=status.HTTP_200_OK
            )

        data = self.get_serializer(shift).data
        return Response(
            {
                "is_active": True,
                "shift": data
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'], url_path='start_day')
    def start_day(self, request):
        user = request.user
        today = timezone.localdate()

        open_shift = self._get_open_shift(user)
        if open_shift:
            return Response(
                {
                    "detail": "Рабочий день уже начат.",
                    "shift": self.get_serializer(open_shift).data
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
        """
        Завершение дня:
        - для менеджера отчет обязателен,
        - для админа отчет НЕ обязателен,
        - если админ все же передал отчет, он сохранится.
        """
        user = request.user
        today = timezone.localdate()
        is_admin = self._is_admin(user)
        shift = self._get_open_shift(user)

        if not shift:
            return Response(
                {"detail": "Нет активной смены для завершения."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from reports.models import DailyReport
        from reports.serializers import DailyReportSerializer

        raw_report = request.data.get('report')
        if not isinstance(raw_report, dict):
            raw_report = request.data if isinstance(request.data, dict) else {}

        has_report_payload = any(
            key in raw_report
            for key in ['content', 'income', 'expense', 'leads_processed', 'deals_closed']
        )

        report_instance = DailyReport.objects.filter(employee=user, date=today).first()

        if has_report_payload:
            payload = {
                'date': str(today),
                'content': (raw_report.get('content') or '').strip(),
                'income': raw_report.get('income', 0),
                'expense': raw_report.get('expense', 0),
                'leads_processed': raw_report.get('leads_processed', 0),
                'deals_closed': raw_report.get('deals_closed', 0),
            }

            if report_instance:
                serializer = DailyReportSerializer(
                    report_instance,
                    data=payload,
                    partial=True,
                    context={'request': request},
                )
            else:
                serializer = DailyReportSerializer(
                    data=payload,
                    context={'request': request},
                )

            serializer.is_valid(raise_exception=True)
            report_instance = serializer.save(employee=user)

        if not is_admin:
            if not report_instance:
                return Response(
                    {"detail": "Сначала заполните ежедневный отчёт."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if not str(report_instance.content or '').strip():
                return Response(
                    {"detail": "Отчёт пустой. Напишите, что было сделано за день."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        shift.time_out = timezone.now()
        shift.save()

        response_payload = {
            "detail": "Рабочий день завершён, отчёт сохранён." if report_instance else "Рабочий день завершён.",
            "shift": self.get_serializer(shift).data,
            "report": DailyReportSerializer(report_instance, context={'request': request}).data if report_instance else None,
        }

        return Response(response_payload, status=status.HTTP_200_OK)