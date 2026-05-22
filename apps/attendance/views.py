from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.permissions import get_employee_profile, is_erp_admin
from apps.organizations.models import Company, Office

from .models import AttendanceReminder, AutoCloseLog, DailyReport, WorkDay
from .serializers import (
    AttendanceReminderSerializer,
    AutoCloseLogSerializer,
    DailyReportSerializer,
    WorkDaySerializer,
)


def employee_scope_filters(user):
    if is_erp_admin(user):
        return Q()

    employee = get_employee_profile(user)
    if not employee:
        return Q(employee=user)

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None

    if role_type == 'company_owner' or (access and access.can_see_all_company):
        return Q(company=employee.company)

    if role_type == 'office_director' or (access and access.can_see_all_office):
        if employee.office_id:
            return Q(company=employee.company, office=employee.office)
        return Q(company=employee.company)

    return Q(employee=user)


def resolve_company_office(user, data=None):
    data = data or {}
    employee = get_employee_profile(user)
    if employee:
        return employee.company, employee.office

    company_id = data.get('company')
    if not company_id:
        raise ValidationError({'company': 'Company is required for users without EmployeeProfile.'})

    company = Company.objects.filter(pk=company_id).first()
    if not company:
        raise ValidationError({'company': 'Company not found.'})
    office = None
    office_id = data.get('office')
    if office_id:
        office = Office.objects.filter(pk=office_id, company=company).first()
        if not office:
            raise ValidationError({'office': 'Office does not belong to selected company.'})
    return company, office


def apply_common_filters(qs, request, *, date_field='date', search_fields=()):
    company = request.query_params.get('company')
    if company:
        qs = qs.filter(company_id=company)

    office = request.query_params.get('office')
    if office:
        qs = qs.filter(office_id=office)

    employee = request.query_params.get('employee') or request.query_params.get('manager')
    if employee:
        qs = qs.filter(employee_id=employee)

    status_value = request.query_params.get('status')
    if status_value and hasattr(qs.model, 'status'):
        qs = qs.filter(status=status_value)

    date_from = request.query_params.get('date_from')
    if date_from:
        qs = qs.filter(**{f'{date_field}__gte': date_from})

    date_to = request.query_params.get('date_to')
    if date_to:
        qs = qs.filter(**{f'{date_field}__lte': date_to})

    search = request.query_params.get('search')
    if search and search_fields:
        query = Q()
        for field in search_fields:
            query |= Q(**{f'{field}__icontains': search})
        qs = qs.filter(query)

    return qs


class WorkDayViewSet(viewsets.ModelViewSet):
    serializer_class = WorkDaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = WorkDay.objects.select_related('company', 'office', 'employee', 'daily_report').prefetch_related('sessions')
        qs = qs.filter(employee_scope_filters(self.request.user))
        qs = apply_common_filters(
            qs,
            self.request,
            search_fields=('employee__email', 'employee__first_name', 'employee__last_name', 'comment'),
        )
        return qs.order_by('-date', '-created_at')

    def perform_create(self, serializer):
        company, office = resolve_company_office(self.request.user, self.request.data)
        serializer.save(company=company, office=office, employee=self.request.user)

    def get_or_create_today(self, request):
        today = timezone.localdate()
        company, office = resolve_company_office(request.user, request.data if request.method == 'POST' else request.query_params)
        workday, _ = WorkDay.objects.get_or_create(
            company=company,
            employee=request.user,
            date=today,
            defaults={
                'office': office,
                'status': WorkDay.STATUS_NOT_STARTED,
            },
        )
        if office and workday.office_id != office.id:
            workday.office = office
            workday.save(update_fields=['office', 'updated_at'])
        return workday

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        workday = self.get_or_create_today(request)
        return Response(self.get_serializer(workday).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='start')
    def start(self, request):
        workday = self.get_or_create_today(request)
        workday.start(note=request.data.get('note', ''))
        return Response(self.get_serializer(workday).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='report')
    def report(self, request):
        workday = self.get_or_create_today(request)
        if workday.status in {WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED}:
            raise ValidationError({'detail': 'Closed workday cannot accept a report.'})

        content = request.data.get('content') or request.data.get('report') or ''
        if not str(content).strip():
            raise ValidationError({'content': 'Daily report content is required.'})

        report = workday.submit_report(
            content=content,
            results=request.data.get('results', ''),
            plans=request.data.get('plans', ''),
            problems=request.data.get('problems', ''),
            leads_processed=request.data.get('leads_processed', 0) or 0,
            deals_closed=request.data.get('deals_closed', 0) or 0,
            comment=request.data.get('comment', ''),
        )
        return Response(
            {
                'workday': self.get_serializer(workday).data,
                'report': DailyReportSerializer(report, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='close')
    def close(self, request):
        workday = self.get_or_create_today(request)
        if workday.status in {WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED}:
            return Response(self.get_serializer(workday).data, status=status.HTTP_200_OK)

        if workday.report_required and not workday.has_report and not is_erp_admin(request.user):
            raise ValidationError({'detail': 'Submit daily report before closing the workday.'})

        workday.close(user=request.user, comment=request.data.get('comment', ''))
        return Response(self.get_serializer(workday).data, status=status.HTTP_200_OK)


class DailyReportViewSet(viewsets.ModelViewSet):
    serializer_class = DailyReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DailyReport.objects.select_related('workday', 'company', 'office', 'employee')
        qs = qs.filter(employee_scope_filters(self.request.user))
        qs = apply_common_filters(
            qs,
            self.request,
            search_fields=('employee__email', 'employee__first_name', 'employee__last_name', 'content', 'results', 'plans', 'problems'),
        )
        return qs.order_by('-date', '-submitted_at')

    def perform_create(self, serializer):
        workday = serializer.validated_data['workday']
        if not is_erp_admin(self.request.user) and workday.employee_id != self.request.user.id:
            raise ValidationError({'workday': 'You can submit a report only for your own workday.'})
        serializer.save(company=workday.company, office=workday.office, employee=workday.employee, date=workday.date)
        if workday.status not in WorkDay.FINAL_STATUSES:
            workday.status = WorkDay.STATUS_REPORT_SUBMITTED
            workday.save(update_fields=['status', 'updated_at'])


class AttendanceReminderViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = AttendanceReminder.objects.select_related('company', 'office', 'employee', 'created_by')
        if not is_erp_admin(self.request.user):
            employee = get_employee_profile(self.request.user)
            if not employee:
                qs = qs.filter(employee=self.request.user)
            else:
                qs = qs.filter(Q(company=employee.company), Q(office=employee.office) | Q(office__isnull=True))
        return apply_common_filters(qs, self.request, search_fields=('message', 'employee__email')).order_by('scheduled_time')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AutoCloseLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AutoCloseLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = AutoCloseLog.objects.select_related('workday', 'company', 'office', 'employee')
        qs = qs.filter(employee_scope_filters(self.request.user))
        return apply_common_filters(qs, self.request, date_field='created_at', search_fields=('reason', 'error_message', 'employee__email')).order_by('-created_at')
