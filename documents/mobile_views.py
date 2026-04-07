from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.permissions import is_admin_user
from .mobile_serializers import GeneratedDocumentMobileSerializer
from .models import GeneratedDocument
from .review_models import DocumentReview, resolve_document_status
from .watermarking import build_approved_document


class GeneratedDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = GeneratedDocumentMobileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = GeneratedDocument.objects.select_related(
            'template',
            'manager',
            'deal',
            'deal__client',
            'review',
            'approved_by',
        ).all()

        if not is_admin_user(self.request.user):
            qs = qs.filter(manager=self.request.user)

        status_param = (self.request.query_params.get('status') or '').strip().lower()
        if status_param == 'approved':
            qs = qs.filter(review__status='approved')
        elif status_param == 'rejected':
            qs = qs.filter(review__status='rejected')
        elif status_param == 'pending':
            qs = qs.exclude(review__status__in=['approved', 'rejected'])
        elif status_param == 'error':
            qs = qs.filter(status='error')

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        manager = self.request.user
        requested_manager = serializer.validated_data.get('manager')
        if is_admin_user(self.request.user) and requested_manager:
            manager = requested_manager

        document = serializer.save(manager=manager)

        if not document.title:
            if document.deal_id and document.deal and getattr(document.deal, 'client', None):
                client = document.deal.client
                client_name = getattr(client, 'full_name', None) or (
                    f"{getattr(client, 'first_name', '')} {getattr(client, 'last_name', '')}".strip()
                )
                document.title = f"{document.template.title} — {client_name or 'Клиент'}"
            else:
                document.title = document.template.title
            document.save(update_fields=['title', 'updated_at'])

        review, _ = DocumentReview.objects.get_or_create(document=document)

        try:
            success, _ = document.generate_document()
            if not success:
                document.refresh_from_db()
                return

            document.status = 'generated'
            document.save(update_fields=['status', 'updated_at'])

            if review.approved_file:
                review.approved_file.delete(save=False)
                review.approved_file = None

            review.status = 'pending'
            review.rejection_reason = ''
            review.reviewed_by = None
            review.reviewed_at = None
            review.save()
        except Exception:
            document.status = 'error'
            document.save(update_fields=['status', 'updated_at'])
            raise

    def perform_update(self, serializer):
        instance = serializer.instance
        if resolve_document_status(instance) == 'approved':
            raise permissions.PermissionDenied('Нельзя менять одобренный документ')

        document = serializer.save()
        review, _ = DocumentReview.objects.get_or_create(document=document)

        if review.approved_file:
            review.approved_file.delete(save=False)
            review.approved_file = None

        review.status = 'pending'
        review.rejection_reason = ''
        review.reviewed_by = None
        review.reviewed_at = None
        review.save()

    def perform_destroy(self, instance):
        if resolve_document_status(instance) == 'approved':
            raise permissions.PermissionDenied('Нельзя удалять одобренный документ')
        instance.delete()

    @action(detail=True, methods=['post'], url_path='regenerate')
    def regenerate(self, request, pk=None):
        document = self.get_object()
        if resolve_document_status(document) == 'approved':
            return Response({'detail': 'Одобренный документ нельзя перегенерировать'}, status=400)

        review, _ = DocumentReview.objects.get_or_create(document=document)
        try:
            success, msg = document.generate_document()
            if not success:
                document.refresh_from_db()
                return Response({'detail': msg}, status=400)

            document.status = 'generated'
            document.save(update_fields=['status', 'updated_at'])

            if review.approved_file:
                review.approved_file.delete(save=False)
                review.approved_file = None

            review.status = 'pending'
            review.rejection_reason = ''
            review.reviewed_by = None
            review.reviewed_at = None
            review.save()
        except Exception as exc:
            document.status = 'error'
            document.save(update_fields=['status', 'updated_at'])
            return Response({'detail': str(exc)}, status=500)

        return Response(self.get_serializer(document, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        document = self.get_object()
        if not is_admin_user(request.user):
            return Response({'detail': 'Только админ может одобрять документы'}, status=403)

        if resolve_document_status(document) == 'approved':
            return Response({'detail': 'Документ уже одобрен'}, status=400)

        if getattr(document, 'status', None) != 'generated' or not getattr(document, 'generated_file', None):
            return Response({'detail': 'Документ ещё не сгенерирован'}, status=400)

        review, _ = DocumentReview.objects.get_or_create(document=document)

        approved_file = build_approved_document(document)
        if approved_file is None:
            return Response(
                {'detail': 'Не удалось собрать approved-файл с watermark. Проверь DOCUMENT_WATERMARK_IMAGE.'},
                status=500,
            )

        with transaction.atomic():
            if review.approved_file:
                review.approved_file.delete(save=False)

            review.mark_approved(user=request.user, approved_file=approved_file)
            document.status = 'approved'
            document.approved_by = request.user
            document.approved_at = review.reviewed_at
            document.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        return Response(self.get_serializer(document, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        document = self.get_object()
        if not is_admin_user(request.user):
            return Response({'detail': 'Только админ может отклонять документы'}, status=403)

        reason = request.data.get('reason', '')
        review, _ = DocumentReview.objects.get_or_create(document=document)

        if review.approved_file:
            review.approved_file.delete(save=False)
            review.approved_file = None

        review.mark_rejected(user=request.user, reason=reason)
        document.status = 'generated'
        document.approved_by = None
        document.approved_at = None
        document.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
        return Response(self.get_serializer(document, context={'request': request}).data)