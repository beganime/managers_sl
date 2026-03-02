# analytics/views.py
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from .models import Deal, Payment, Expense
from .serializers import DealSerializer, PaymentSerializer, ExpenseSerializer

class BaseAnalyticsViewSet(viewsets.ModelViewSet):
    """Базовый класс для фильтрации по менеджеру и оффлайн-синхронизации"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # Суперюзер видит все, менеджер — только свои записи
        qs = self.queryset.all() if user.is_superuser else self.queryset.filter(manager=user)
            
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
                
        return qs.order_by('-updated_at')

    def perform_create(self, serializer):
        # Жестко фиксируем, что сделку/платеж создал именно этот менеджер
        serializer.save(manager=self.request.user)

class DealViewSet(BaseAnalyticsViewSet):
    # prefetch_related ускоряет загрузку, чтобы не было 100 запросов к БД при выводе платежей
    queryset = Deal.objects.prefetch_related('payments').all()
    serializer_class = DealSerializer

class PaymentViewSet(BaseAnalyticsViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

class ExpenseViewSet(BaseAnalyticsViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer