# documents/views.py
import logging

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import InfoSnippet, DocumentTemplate, GeneratedDocument, KnowledgeTest
from .serializers import (
    InfoSnippetSerializer,
    DocumentTemplateSerializer,
    GeneratedDocumentSerializer,
    KnowledgeTestSerializer,
)

logger = logging.getLogger(__name__)


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or getattr(user, 'role', None) == 'admin'
        )
    )


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
        qs = GeneratedDocument.objects.select_related(
            'template',
            'manager',
            'deal',
            'deal__client',
            'approved_by',
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

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        request_user = self.request.user
        deal = serializer.validated_data.get('deal')

        owner = deal.manager if (deal and is_admin_user(request_user)) else request_user
        document = serializer.save(manager=owner)

        if not document.title:
            if document.deal_id and document.deal:
                document.title = f"{document.template.title} — {document.deal.client.full_name}"
            else:
                document.title = document.template.title
            document.save(update_fields=['title', 'updated_at'])

        success, msg = document.generate_document()
        if not success:
            logger.error(f"Ошибка авто-генерации документа #{document.id}: {msg}")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == 'approved':
            raise ValidationError('Одобренный документ редактировать нельзя.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == 'approved':
            raise ValidationError('Одобренный документ редактировать нельзя.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status == 'approved':
            raise ValidationError('Одобренный документ удалять нельзя.')
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        if not is_admin_user(request.user):
            raise PermissionDenied('Только администратор может одобрять документы.')

        doc = self.get_object()

        if doc.status != 'generated':
            return Response(
                {'detail': 'Одобрять можно только корректно сгенерированный документ.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not doc.generated_file:
            return Response(
                {'detail': 'У документа отсутствует готовый файл.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc.status = 'approved'
        doc.approved_by = request.user
        doc.approved_at = timezone.now()
        doc.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        return Response({
            'detail': 'Документ одобрен.',
            'document': self.get_serializer(doc).data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='regenerate')
    def regenerate(self, request, pk=None):
        doc = self.get_object()

        if not is_admin_user(request.user) and doc.manager_id != request.user.id:
            raise PermissionDenied('Нет прав на перегенерацию документа.')

        success, msg = doc.generate_document()
        doc.refresh_from_db()

        return Response({
            'detail': msg,
            'document': self.get_serializer(doc).data
        }, status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        doc = self.get_object()

        if not doc.can_download:
            return Response(
                {'detail': 'Скачивание доступно только после одобрения администратором.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response({
            'file_url': self.get_serializer(doc).data.get('file_url')
        }, status=status.HTTP_200_OK)


class KnowledgeTestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = KnowledgeTestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return KnowledgeTest.objects.filter(is_active=True).prefetch_related('questions')