# documents/views.py
import logging
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.dateparse import parse_datetime

from .models import InfoSnippet, DocumentTemplate, GeneratedDocument, KnowledgeTest
from .serializers import (
    InfoSnippetSerializer, DocumentTemplateSerializer,
    GeneratedDocumentSerializer, KnowledgeTestSerializer,
)

logger = logging.getLogger(__name__)


class InfoSnippetViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = InfoSnippetSerializer
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
    serializer_class   = DocumentTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DocumentTemplate.objects.filter(is_active=True).prefetch_related('fields')
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')


class GeneratedDocumentViewSet(viewsets.ModelViewSet):
    serializer_class   = GeneratedDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = (
            GeneratedDocument.objects.all()
            if user.is_superuser
            else GeneratedDocument.objects.filter(manager=user)
        )
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
        except Exception as e:
            logger.error(f"Ошибка авто-генерации документа #{document.id}: {e}")

    # ── Одобрение документа администратором ──────────────────────────────────
    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        """POST /api/documents/generated/{id}/approve/  — только суперадмин"""
        doc = self.get_object()
        if doc.status not in ('generated', 'error'):
            return Response(
                {'detail': 'Документ уже одобрен или не сгенерирован.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        doc.status      = 'approved'
        doc.approved_by = request.user
        doc.approved_at = timezone.now()
        doc.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        return Response(self.get_serializer(doc).data)


# ─── Тесты ───────────────────────────────────────────────────────────────────

class KnowledgeTestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class   = KnowledgeTestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return KnowledgeTest.objects.filter(is_active=True).prefetch_related('questions')