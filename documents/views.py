# documents/views.py
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from .models import InfoSnippet, ContractTemplate, Contract
from .serializers import InfoSnippetSerializer, ContractTemplateSerializer, ContractSerializer

class InfoSnippetViewSet(viewsets.ReadOnlyModelViewSet):
    """API для Базы знаний (скрипты, ссылки, реквизиты). Только чтение."""
    serializer_class = InfoSnippetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = InfoSnippet.objects.all()
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('category', 'order')

class ContractTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    """API для Шаблонов договоров. Только чтение."""
    serializer_class = ContractTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ContractTemplate.objects.all()
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')

class ContractViewSet(viewsets.ModelViewSet):
    """API для запросов на создание договоров (черновиков)."""
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Contract.objects.all() if user.is_superuser else Contract.objects.filter(manager=user)
        
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        # Менеджер, создавший запрос, привязывается автоматически
        serializer.save(manager=self.request.user)