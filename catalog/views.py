# catalog/views.py
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from .models import Currency, University, Program
from .serializers import CurrencySerializer, UniversitySerializer, ProgramSerializer

# Используем ReadOnlyModelViewSet, чтобы менеджеры с телефонов могли только ЧИТАТЬ каталог
class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CurrencySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Currency.objects.all()
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')

class UniversityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UniversitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Подтягиваем связанные программы для оптимизации SQL (чтобы не было проблемы N+1)
        qs = University.objects.prefetch_related('programs').all()
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')