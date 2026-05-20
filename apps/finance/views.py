from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import filter_by_company_scope, filter_by_office_scope, get_employee_profile, is_erp_admin

from .models import (
    Cashbox,
    Deal,
    EmployeeCommission,
    Expense,
    ExpenseCategory,
    FinancialPeriod,
    Income,
    Payment,
    Transaction,
)
from .serializers import (
    CashboxSerializer,
    DealSerializer,
    EmployeeCommissionSerializer,
    ExpenseCategorySerializer,
    ExpenseSerializer,
    FinancialPeriodSerializer,
    IncomeSerializer,
    PaymentSerializer,
    TransactionSerializer,
)


TRUE_VALUES = {'1', 'true', 'True', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'False', 'no', 'off'}


def parse_bool(value):
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


def apply_common_filters(qs, request, *, date_field=None, status_field=None, manager_field=None, client_field=None, search_fields=()):
    company = request.query_params.get('company')
    if company:
        qs = qs.filter(company_id=company)

    office = request.query_params.get('office')
    if office:
        qs = qs.filter(office_id=office)

    manager = request.query_params.get('manager')
    if manager and manager_field:
        qs = qs.filter(**{f'{manager_field}_id': manager})

    client = request.query_params.get('client')
    if client and client_field:
        qs = qs.filter(**{f'{client_field}_id': client})

    status_value = request.query_params.get('status')
    if status_value and status_field:
        qs = qs.filter(**{status_field: status_value})

    is_confirmed = parse_bool(request.query_params.get('is_confirmed'))
    if is_confirmed is not None and hasattr(qs.model, 'is_confirmed'):
        qs = qs.filter(is_confirmed=is_confirmed)

    date_from = request.query_params.get('date_from')
    if date_from and date_field:
        qs = qs.filter(**{f'{date_field}__gte': date_from})

    date_to = request.query_params.get('date_to')
    if date_to and date_field:
        qs = qs.filter(**{f'{date_field}__lte': date_to})

    search = request.query_params.get('search')
    if search and search_fields:
        query = Q()
        for field in search_fields:
            query |= Q(**{f'{field}__icontains': search})
        qs = qs.filter(query)

    return qs


def scoped_queryset(qs, user, *, has_office=True):
    if has_office:
        return filter_by_office_scope(qs, user)
    return filter_by_company_scope(qs, user)


def default_company_office(user):
    employee = get_employee_profile(user)
    if not employee:
        return {}
    data = {'company': employee.company}
    if employee.office_id:
        data['office'] = employee.office
    return data


class CashboxViewSet(viewsets.ModelViewSet):
    serializer_class = CashboxSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Cashbox.objects.select_related('company', 'office', 'currency')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(qs, self.request, search_fields=('name', 'company__name', 'office__name', 'office__city'))
        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs.order_by('company__name', 'office__name', 'name')

    def perform_create(self, serializer):
        if is_erp_admin(self.request.user) or serializer.validated_data.get('company'):
            serializer.save()
            return
        serializer.save(**default_company_office(self.request.user))


class DealViewSet(viewsets.ModelViewSet):
    serializer_class = DealSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Deal.objects.select_related('company', 'office', 'client', 'application', 'manager', 'service', 'currency')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(
            qs,
            self.request,
            date_field='created_at',
            status_field='payment_status',
            manager_field='manager',
            client_field='client',
            search_fields=('title', 'client__full_name', 'client__phone', 'university_name', 'program_name', 'service__title'),
        )
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        data = {}
        if not is_erp_admin(self.request.user):
            data.update(default_company_office(self.request.user))
        if not serializer.validated_data.get('manager'):
            data['manager'] = self.request.user
        serializer.save(**data)


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Payment.objects.select_related('company', 'office', 'deal', 'client', 'manager', 'cashbox', 'currency', 'confirmed_by')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(
            qs,
            self.request,
            date_field='payment_date',
            manager_field='manager',
            client_field='client',
            search_fields=('client__full_name', 'client__phone', 'deal__title', 'comment'),
        )
        return qs.order_by('-payment_date', '-created_at')

    def perform_create(self, serializer):
        data = {}
        if not is_erp_admin(self.request.user):
            data.update(default_company_office(self.request.user))
        if not serializer.validated_data.get('manager'):
            data['manager'] = self.request.user
        serializer.save(**data)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, pk=None):
        payment = self.get_object()
        payment.confirm(user=request.user)
        return Response(PaymentSerializer(payment, context={'request': request}).data, status=status.HTTP_200_OK)


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ExpenseCategory.objects.select_related('company')
        qs = scoped_queryset(qs, self.request.user, has_office=False)
        qs = apply_common_filters(qs, self.request, search_fields=('name', 'code', 'company__name'))
        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs.order_by('company__name', 'name')

    def perform_create(self, serializer):
        if is_erp_admin(self.request.user) or serializer.validated_data.get('company'):
            serializer.save()
            return
        serializer.save(company=default_company_office(self.request.user).get('company'))


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Expense.objects.select_related('company', 'office', 'category', 'employee', 'cashbox', 'currency', 'confirmed_by')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(
            qs,
            self.request,
            date_field='date',
            search_fields=('title', 'comment', 'category__name', 'employee__email'),
        )
        employee = self.request.query_params.get('manager')
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs.order_by('-date', '-created_at')

    def perform_create(self, serializer):
        data = {}
        if not is_erp_admin(self.request.user):
            data.update(default_company_office(self.request.user))
        serializer.save(**data)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm(self, request, pk=None):
        expense = self.get_object()
        expense.confirm(user=request.user)
        return Response(ExpenseSerializer(expense, context={'request': request}).data, status=status.HTTP_200_OK)


class IncomeViewSet(viewsets.ModelViewSet):
    serializer_class = IncomeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Income.objects.select_related('company', 'office', 'cashbox', 'currency')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(
            qs,
            self.request,
            date_field='date',
            search_fields=('title', 'source', 'comment'),
        )
        return qs.order_by('-date', '-created_at')

    def perform_create(self, serializer):
        data = {}
        if not is_erp_admin(self.request.user):
            data.update(default_company_office(self.request.user))
        serializer.save(**data)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Transaction.objects.select_related('company', 'office', 'cashbox', 'currency', 'related_payment', 'related_expense', 'created_by')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(
            qs,
            self.request,
            date_field='created_at',
            status_field='transaction_type',
            search_fields=('comment', 'related_payment__client__full_name', 'related_expense__title'),
        )
        return qs.order_by('-created_at')


class EmployeeCommissionViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeCommissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = EmployeeCommission.objects.select_related('company', 'office', 'employee', 'payment', 'deal', 'approved_by')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(
            qs,
            self.request,
            date_field='created_at',
            status_field='status',
            manager_field='employee',
            search_fields=('employee__email', 'deal__title', 'payment__client__full_name'),
        )
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        data = {}
        if not is_erp_admin(self.request.user):
            data.update(default_company_office(self.request.user))
        serializer.save(**data)


class FinancialPeriodViewSet(viewsets.ModelViewSet):
    serializer_class = FinancialPeriodSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = FinancialPeriod.objects.select_related('company', 'office', 'closed_by')
        qs = scoped_queryset(qs, self.request.user)
        qs = apply_common_filters(
            qs,
            self.request,
            date_field='start_date',
            search_fields=('company__name', 'office__name', 'office__city'),
        )
        status_value = self.request.query_params.get('status')
        if status_value == 'closed':
            qs = qs.filter(is_closed=True)
        elif status_value == 'open':
            qs = qs.filter(is_closed=False)
        return qs.order_by('-start_date')

    def perform_create(self, serializer):
        if is_erp_admin(self.request.user) or serializer.validated_data.get('company'):
            serializer.save()
            return
        serializer.save(**default_company_office(self.request.user))

    @action(detail=True, methods=['post'], url_path='calculate')
    def calculate(self, request, pk=None):
        period = self.get_object()
        period.calculate()
        return Response(FinancialPeriodSerializer(period, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        period = self.get_object()
        period.close(user=request.user)
        return Response(FinancialPeriodSerializer(period, context={'request': request}).data, status=status.HTTP_200_OK)
