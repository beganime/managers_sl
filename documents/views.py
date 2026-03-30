import logging

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from django.db import ProgrammingError, OperationalError
from rest_framework.exceptions import APIException


from .models import (
    InfoSnippet,
    DocumentTemplate,
    GeneratedDocument,
    KnowledgeTest,
    KnowledgeTestAttempt,
)
from .serializers import (
    InfoSnippetSerializer,
    DocumentTemplateSerializer,
    GeneratedDocumentSerializer,
    KnowledgeTestSerializer,
    KnowledgeTestAttemptSerializer,
)

logger = logging.getLogger(__name__)


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or getattr(user, 'role', None) == 'admin' or user.is_staff
        )
    )


class InfoSnippetViewSet(viewsets.ModelViewSet):
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

    def perform_create(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может добавлять записи.')
        serializer.save()

    def perform_update(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может изменять записи.')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может удалять записи.')
        instance.delete()


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

        return Response(
            {
                'detail': 'Документ одобрен.',
                'document': self.get_serializer(doc).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='regenerate')
    def regenerate(self, request, pk=None):
        doc = self.get_object()

        if not is_admin_user(request.user) and doc.manager_id != request.user.id:
            raise PermissionDenied('Нет прав на перегенерацию документа.')

        success, msg = doc.generate_document()
        doc.refresh_from_db()

        return Response(
            {
                'detail': msg,
                'document': self.get_serializer(doc).data,
            },
            status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        doc = self.get_object()

        if not doc.can_download:
            return Response(
                {'detail': 'Скачивание доступно только после одобрения администратором.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {'file_url': self.get_serializer(doc).data.get('file_url')},
            status=status.HTTP_200_OK,
        )


class KnowledgeTestViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeTestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = KnowledgeTest.objects.filter(is_active=True).prefetch_related('questions')

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может создавать тесты.')
        serializer.save()

    def perform_update(self, serializer):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может изменять тесты.')
        serializer.save()

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied('Только администратор может удалять тесты.')
        instance.delete()

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        test = self.get_object()
        submitted_answers = request.data.get('answers', {})

        if not isinstance(submitted_answers, dict):
            raise ValidationError({'answers': 'answers должен быть объектом вида {"question_id": index}.'})

        questions = list(test.questions.all())
        total = len(questions)
        score = 0
        normalized_answers = {}

        for idx, question in enumerate(questions):
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
                "Knowledge test submit failed because attempts table is missing or unavailable. "
                "test_id=%s user_id=%s",
                test.id,
                request.user.id,
            )
            raise APIException(
                "Таблица результатов тестов не создана на сервере. "
                "Нужно применить миграции documents."
            ) from exc

        return Response(
            {
                'detail': 'Результат сохранён.',
                'attempt': KnowledgeTestAttemptSerializer(attempt, context={'request': request}).data,
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