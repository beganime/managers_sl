from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import DailyReport
from .serializers import DailyReportSerializer

try:
    from .ai_summary import build_admin_ai_summary
except Exception:  # pragma: no cover
    build_admin_ai_summary = None


def is_admin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or getattr(user, "role", None) == "admin"
            or user.is_staff
        )
    )


class DailyReportViewSet(viewsets.ModelViewSet):
    serializer_class = DailyReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        is_admin = is_admin_user(user)

        qs = (
            DailyReport.objects.select_related("employee", "employee__office").all()
            if is_admin
            else DailyReport.objects.select_related("employee", "employee__office").filter(employee=user)
        )

        updated_after = self.request.query_params.get("updated_after")
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        employee_id = self.request.query_params.get("employee")
        if employee_id and is_admin:
            qs = qs.filter(employee_id=employee_id)

        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(date__lte=date_to)

        office_id = self.request.query_params.get("office")
        if office_id and is_admin:
            qs = qs.filter(employee__office_id=office_id)

        return qs.order_by("-date", "-id")

    def perform_create(self, serializer):
        serializer.save(employee=self.request.user)

    @action(detail=False, methods=["get"], url_path="today")
    def check_today(self, request):
        today = timezone.localdate()
        report = self.get_queryset().filter(date=today).first()

        if report:
            return Response(self.get_serializer(report).data)

        return Response(
            {"detail": "Отчёт за сегодня не найден"},
            status=status.HTTP_404_NOT_FOUND,
        )

    @action(detail=False, methods=["post"], url_path="submit_today")
    def submit_today(self, request):
        today = timezone.localdate()
        existing = DailyReport.objects.filter(employee=request.user, date=today).first()

        if existing:
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(
                {
                    "detail": "Отчёт за сегодня обновлён.",
                    "report": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        payload = request.data.copy()
        payload["date"] = str(today)

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(employee=request.user)

        return Response(
            {
                "detail": "Отчёт за сегодня создан.",
                "report": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="ai_summary")
    def ai_summary(self, request):
        if not is_admin_user(request.user):
            return Response(
                {"detail": "Только администратор может получать AI summary."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if build_admin_ai_summary is None:
            return Response(
                {"detail": "AI summary helper не найден на сервере."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        office_id = request.query_params.get("office")

        office_id = int(office_id) if office_id and str(office_id).isdigit() else None

        result = build_admin_ai_summary(
            date_from=date_from,
            date_to=date_to,
            office_id=office_id,
        )

        return Response(result, status=status.HTTP_200_OK)