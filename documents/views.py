# documents/views.py
from rest_framework import viewsets, permissions
from django.utils.dateparse import parse_datetime
from .models import InfoSnippet, DocumentTemplate, GeneratedDocument
from .serializers import InfoSnippetSerializer, DocumentTemplateSerializer, GeneratedDocumentSerializer

class InfoSnippetViewSet(viewsets.ReadOnlyModelViewSet):
    """API для Базы знаний. Только чтение."""
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
    """API для получения доступных шаблонов документов. Только чтение."""
    serializer_class = DocumentTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DocumentTemplate.objects.filter(is_active=True)
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')

class GeneratedDocumentViewSet(viewsets.ModelViewSet):
    """API для создания и просмотра сгенерированных документов менеджером."""
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
        # 1. Привязываем документ к текущему менеджеру и сохраняем
        document = serializer.save(manager=self.request.user)
        
        # 2. Мгновенно пытаемся сгенерировать DOCX файл
        try:
            document.generate_document()
        except Exception:
            pass # Если ошибка генерации, статус просто станет 'error'