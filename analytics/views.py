# analytics/views.py
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Deal, Payment, Expense, FinancialPeriod
from .serializers import (
    DealSerializer,
    PaymentSerializer,
    ExpenseSerializer,
    FinancialPeriodSerializer,
)
from .services import BillingService


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or getattr(user, 'role', None) == 'admin'
        )
    )


class DealViewSet(viewsets.ModelViewSet):
    serializer_class = DealSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Deal.objects.select_related(
            'client',
            'manager',
            'university',
            'program',
            'service_ref',
            'currency',
        ).prefetch_related('payments')

        if not is_admin_user(user):
            qs = qs.filter(manager=user)

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)

        payment_status = self.request.query_params.get('payment_status')
        if payment_status:
            qs = qs.filter(payment_status=payment_status)

        deal_type = self.request.query_params.get('deal_type')
        if deal_type:
            qs = qs.filter(deal_type=deal_type)

        manager_id = self.request.query_params.get('manager')
        if manager_id and is_admin_user(user):
            qs = qs.filter(manager_id=manager_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(client__full_name__icontains=search)

        return qs.order_by('-updated_at', '-id')

    def perform_create(self, serializer):
        if is_admin_user(self.request.user):
            serializer.save()
        else:
            serializer.save(manager=self.request.user)


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Payment.objects.select_related(
            'deal',
            'deal__client',
            'manager',
            'currency',
            'confirmed_by',
        )

        if not is_admin_user(user):
            qs = qs.filter(manager=user)

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        deal_id = self.request.query_params.get('deal')
        if deal_id:
            qs = qs.filter(deal_id=deal_id)

        is_confirmed = self.request.query_params.get('is_confirmed')
        if is_confirmed in ('true', 'false', '1', '0'):
            qs = qs.filter(is_confirmed=is_confirmed in ('true', '1'))

        manager_id = self.request.query_params.get('manager')
        if manager_id and is_admin_user(user):
            qs = qs.filter(manager_id=manager_id)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)

        current_period = self.request.query_params.get('current_period')
        if current_period in ('true', '1'):
            period = FinancialPeriod.ensure_current_period()
            qs = qs.filter(payment_date__range=(period.start_date, period.end_date))

        period_start = self.request.query_params.get('period_start')
        if period_start:
            period = FinancialPeriod.objects.filter(start_date=period_start).first()
            if period:
                qs = qs.filter(payment_date__range=(period.start_date, period.end_date))

        return qs.order_by('-payment_date', '-id')

    def perform_create(self, serializer):
        deal = serializer.validated_data['deal']
        payment_manager = deal.manager if is_admin_user(self.request.user) else self.request.user
        serializer.save(manager=payment_manager)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_confirmed:
            raise ValidationError('Подтверждённый платёж редактировать нельзя.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_confirmed:
            raise ValidationError('Подтверждённый платёж редактировать нельзя.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_confirmed:
            raise ValidationError('Подтверждённый платёж удалять нельзя.')
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm_payment(self, request, pk=None):
        if not is_admin_user(request.user):
            raise PermissionDenied('Только администратор может подтверждать платежи.')

        payment = self.get_object()
        BillingService.confirm_payment(payment, request.user)
        payment.refresh_from_db()

        return Response({
            'detail': 'Платёж подтверждён.',
            'payment': self.get_serializer(payment).data
        }, status=status.HTTP_200_OK)


class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Expense.objects.select_related('manager', 'currency')

        if not is_admin_user(user):
            qs = qs.filter(manager=user)

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        manager_id = self.request.query_params.get('manager')
        if manager_id and is_admin_user(user):
            qs = qs.filter(manager_id=manager_id)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)

        current_period = self.request.query_params.get('current_period')
        if current_period in ('true', '1'):
            period = FinancialPeriod.ensure_current_period()
            qs = qs.filter(date__range=(period.start_date, period.end_date))

        period_start = self.request.query_params.get('period_start')
        if period_start:
            period = FinancialPeriod.objects.filter(start_date=period_start).first()
            if period:
                qs = qs.filter(date__range=(period.start_date, period.end_date))

        return qs.order_by('-date', '-id')

    def perform_create(self, serializer):
        serializer.save(manager=self.request.user)


class FinancialPeriodViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FinancialPeriodSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = FinancialPeriod.objects.all().order_by('-start_date')

        is_closed = self.request.query_params.get('is_closed')
        if is_closed in ('true', 'false', '1', '0'):
            qs = qs.filter(is_closed=is_closed in ('true', '1'))

        return qs

    @action(detail=False, methods=['get'], url_path='current')
    def current_period(self, request):
        period = FinancialPeriod.ensure_current_period()
        period.calculate_stats()
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=['post'], url_path='recalculate')
    def recalculate(self, request, pk=None):
        if not is_admin_user(request.user):
            raise PermissionDenied('Только администратор может пересчитывать периоды.')

        period = self.get_object()
        stats = period.calculate_stats()

        return Response({
            'detail': 'Период пересчитан.',
            'period': self.get_serializer(period).data,
            'stats': stats,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='close')
    def close_period(self, request, pk=None):
        if not is_admin_user(request.user):
            raise PermissionDenied('Только администратор может закрывать период.')

        period = self.get_object()
        period.calculate_stats()

        if not period.is_closed:
            period.is_closed = True
            period.save(update_fields=['is_closed', 'updated_at'])

        return Response({
            'detail': 'Период закрыт.',
            'period': self.get_serializer(period).data,
        }, status=status.HTTP_200_OK)