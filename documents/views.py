# documents/views.py
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from .models import InfoSnippet, DocumentTemplate, GeneratedDocument
from .serializers import InfoSnippetSerializer, DocumentTemplateSerializer, GeneratedDocumentSerializer

class InfoSnippetViewSet(viewsets.ReadOnlyModelViewSet):
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

class DocumentTemplateViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DocumentTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Используем prefetch_related для оптимизации запросов (избегаем N+1 проблемы)
        qs = DocumentTemplate.objects.filter(is_active=True).prefetch_related('fields')
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')

class GeneratedDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = GeneratedDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = GeneratedDocument.objects.all() if user.is_superuser else GeneratedDocument.objects.filter(manager=user)
        
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        document = serializer.save(manager=self.request.user)
        try:
            document.generate_document()
        except Exception:
            pass