# documents/views.py
import logging

from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.utils.dateparse import parse_datetime
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.response import Response

from .ai_search import search_knowledge_base
from .models import (
    DocumentReview,
    DocumentTemplate,
    GeneratedDocument,
    InfoSnippet,
    KnowledgeSection,
    KnowledgeSectionAttachment,
    KnowledgeTest,
    KnowledgeTestAttempt,
    resolve_document_status,
)
from .serializers import (
    DocumentTemplateSerializer,
    GeneratedDocumentSerializer,
    InfoSnippetSerializer,
    KnowledgeSectionAttachmentSerializer,
    KnowledgeSectionSerializer,
    KnowledgeTestAttemptSerializer,
    KnowledgeTestSerializer,
)
from .watermarking import build_approved_document


logger = logging.getLogger(__name__)


def is_admin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (
            user.is_superuser
            or getattr(user, 'role', None) == 'admin'
            or user.is_staff
        )
    )


class KnowledgeSectionViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeSectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = (
            KnowledgeSection.objects
            .select_related('parent', 'created_by')
            .prefetch_related('children', 'responsible_users', 'attachments')
            .all()
        )

        parent = self.request.query_params.get('parent')
        if parent == 'null':
            qs = qs.filter(parent__isnull=True)
        elif parent:
            qs = qs.filter(parent_id=parent)

        responsible = self.request.query_params.get('responsible')
        if responsible:
            qs = qs.filter(responsible_users__id=responsible)

        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', '0', 'false'):
            qs = qs.filter(is_active=is_active in ('1', 'true'))

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(external_url__icontains=search)
            )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.distinct().order_by('parent__id', 'order', 'title')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Удалять разделы может только администратор.')
        instance.delete()


class KnowledgeSectionAttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeSectionAttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = KnowledgeSectionAttachment.objects.select_related('section', 'uploaded_by')

        section = self.request.query_params.get('section')
        if section:
            qs = qs.filter(section_id=section)

        attachment_type = self.request.query_params.get('attachment_type')
        if attachment_type:
            qs = qs.filter(attachment_type=attachment_type)

        return qs.order_by('order', '-created_at')

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Удалять файлы/ссылки может только администратор.')
        instance.delete()


class InfoSnippetViewSet(viewsets.ModelViewSet):
    serializer_class = InfoSnippetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = InfoSnippet.objects.select_related('section').all()

        section = self.request.query_params.get('section')
        if section:
            qs = qs.filter(section_id=section)

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(content__icontains=search)
                | Q(section__title__icontains=search)
                | Q(section__description__icontains=search)
            )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.distinct().order_by('section__order', 'category', 'order', 'title')

    def perform_create(self, serializer):
        serializer.save(content_format=serializer.validated_data.get('content_format') or 'markdown')

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Удалять записи базы знаний может только администратор.')
        instance.delete()

    @action(detail=False, methods=['post'], url_path='ask_ai')
    def ask_ai(self, request):
        query = request.data.get('query', '').strip()
        if not query:
            return Response({'detail': 'Введите ваш вопрос'}, status=status.HTTP_400_BAD_REQUEST)

        answer = search_knowledge_base(query)
        return Response({'answer': answer}, status=status.HTTP_200_OK)


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
            'review',
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

        status_value = (self.request.query_params.get('status') or '').strip().lower()
        if status_value:
            if status_value == 'pending':
                qs = qs.exclude(review__status__in=['approved', 'rejected']).exclude(status='error')
            elif status_value == 'approved':
                qs = qs.filter(review__status='approved')
            elif status_value == 'error':
                qs = qs.filter(status='error')
            elif status_value == 'rejected':
                qs = qs.filter(review__status='rejected')
            else:
                qs = qs.filter(status=status_value)

        return qs.order_by('-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        deal = serializer.validated_data.get('deal')
        request_user = request.user

        owner = deal.manager if (deal and is_admin_user(request_user)) else request_user
        document = serializer.save(manager=owner)

        if not document.title:
            if document.deal_id and document.deal and document.deal.client:
                client = document.deal.client
                client_name = getattr(client, 'full_name', None) or (
                    f"{getattr(client, 'first_name', '')} {getattr(client, 'last_name', '')}".strip()
                )
                document.title = f'{document.template.title} — {client_name or "Клиент"}'
            else:
                document.title = document.template.title

            document.save(update_fields=['title', 'updated_at'])

        review, _ = DocumentReview.objects.get_or_create(document=document)

        success, msg = document.generate_document()
        if not success:
            logger.error('Ошибка авто-генерации документа #%s: %s', document.id, msg)
        else:
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

        output = self.get_serializer(document, context={'request': request})
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if resolve_document_status(instance) == 'approved':
            raise ValidationError('Одобренный документ редактировать нельзя.')
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if resolve_document_status(instance) == 'approved':
            raise ValidationError('Одобренный документ редактировать нельзя.')
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if resolve_document_status(instance) == 'approved':
            raise ValidationError('Одобренный документ удалять нельзя.')
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        if not is_admin_user(request.user):
            raise PermissionDenied('Только администратор может одобрять документы.')

        doc = self.get_object()

        if resolve_document_status(doc) == 'approved':
            return Response({'detail': 'Документ уже одобрен.'}, status=status.HTTP_400_BAD_REQUEST)

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

        review, _ = DocumentReview.objects.get_or_create(document=doc)
        approved_file = build_approved_document(doc)

        if approved_file is None:
            return Response(
                {'detail': 'Не удалось собрать approved-файл с watermark. Проверь DOCUMENT_WATERMARK_IMAGE.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        with transaction.atomic():
            if review.approved_file:
                review.approved_file.delete(save=False)

            review.mark_approved(user=request.user, approved_file=approved_file)
            doc.status = 'approved'
            doc.approved_by = request.user
            doc.approved_at = review.reviewed_at
            doc.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        return Response(
            {
                'detail': 'Документ одобрен.',
                'document': self.get_serializer(doc, context={'request': request}).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='regenerate')
    def regenerate(self, request, pk=None):
        doc = self.get_object()

        if resolve_document_status(doc) == 'approved':
            raise ValidationError('Одобренный документ перегенерировать нельзя.')

        if not is_admin_user(request.user) and doc.manager_id != request.user.id:
            raise PermissionDenied('Нет прав на перегенерацию документа.')

        review, _ = DocumentReview.objects.get_or_create(document=doc)
        success, msg = doc.generate_document()
        doc.refresh_from_db()

        if success:
            doc.status = 'generated'
            doc.save(update_fields=['status', 'updated_at'])

            if review.approved_file:
                review.approved_file.delete(save=False)
                review.approved_file = None

            review.status = 'pending'
            review.rejection_reason = ''
            review.reviewed_by = None
            review.reviewed_at = None
            review.save()

        return Response(
            {
                'detail': msg,
                'document': self.get_serializer(doc, context={'request': request}).data,
            },
            status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )

    def _build_download_payload(self, doc, request):
        payload = self.get_serializer(doc, context={'request': request}).data
        return {
            'document_id': doc.id,
            'status': payload.get('status'),
            'review_status': payload.get('review_status'),
            'original_file_url': payload.get('original_file_url') or payload.get('file_url'),
            'approved_file_url': payload.get('approved_file_url'),
            'can_download_original': bool(payload.get('original_file_url') or payload.get('file_url')),
            'can_download_approved': bool(payload.get('approved_file_url')),
        }

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        doc = self.get_object()
        data = self._build_download_payload(doc, request)

        if not data['can_download_original'] and not data['can_download_approved']:
            return Response(
                {'detail': 'У документа пока нет доступных файлов для скачивания.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='download-original')
    def download_original(self, request, pk=None):
        doc = self.get_object()
        payload = self.get_serializer(doc, context={'request': request}).data
        original_url = payload.get('original_file_url') or payload.get('file_url')

        if not original_url:
            return Response(
                {'detail': 'Оригинальный файл без watermark ещё не готов.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                'document_id': doc.id,
                'file_url': original_url,
                'type': 'original',
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['get'], url_path='download-approved')
    def download_approved(self, request, pk=None):
        doc = self.get_object()
        payload = self.get_serializer(doc, context={'request': request}).data
        approved_url = payload.get('approved_file_url')

        if not approved_url:
            return Response(
                {'detail': 'Файл с watermark ещё не одобрен или не собран.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                'document_id': doc.id,
                'file_url': approved_url,
                'type': 'approved',
            },
            status=status.HTTP_200_OK,
        )


class KnowledgeTestViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeTestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = KnowledgeTest.objects.filter(is_active=True).select_related('section').prefetch_related('questions')

        section = self.request.query_params.get('section')
        if section:
            qs = qs.filter(section_id=section)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(section__title__icontains=search)
            )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Удалять тесты может только администратор.')
        instance.delete()

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        test = self.get_object()
        submitted_answers = request.data.get('answers', {})

        if not isinstance(submitted_answers, dict):
            raise ValidationError(
                {'answers': 'answers должен быть объектом вида {"question_id": index}.'}
            )

        questions = list(test.questions.all())
        total = len(questions)
        score = 0
        normalized_answers = {}

        for question in questions:
            qid_str = str(question.id)
            raw_answer = submitted_answers.get(qid_str, submitted_answers.get(question.id))

            if raw_answer is None:
                continue

            try:
                answer_index = int(raw_answer)
            except (TypeError, ValueError):
                continue

            normalized_answers[qid_str] = answer_index
            if answer_index == question.correct:
                score += 1

        try:
            attempt = KnowledgeTestAttempt.objects.create(
                test=test,
                user=request.user,
                score=score,
                total=total,
                answers=normalized_answers,
            )
        except (ProgrammingError, OperationalError) as exc:
            logger.exception(
                'Knowledge test submit failed because attempts table is missing or unavailable. test_id=%s user_id=%s',
                test.id,
                request.user.id,
            )
            raise APIException(
                'Таблица результатов тестов не создана на сервере. Нужно применить миграции documents.'
            ) from exc

        return Response(
            {
                'detail': 'Результат сохранён.',
                'attempt': KnowledgeTestAttemptSerializer(
                    attempt, context={'request': request}
                ).data,
                'score': score,
                'total': total,
            },
            status=status.HTTP_201_CREATED,
        )


class KnowledgeTestAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = KnowledgeTestAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = KnowledgeTestAttempt.objects.select_related('user', 'test')

        if not is_admin_user(self.request.user):
            qs = qs.filter(user=self.request.user)

        test_id = self.request.query_params.get('test')
        if test_id:
            qs = qs.filter(test_id=test_id)

        user_id = self.request.query_params.get('user')
        if user_id and is_admin_user(self.request.user):
            qs = qs.filter(user_id=user_id)

        return qs.order_by('-completed_at')