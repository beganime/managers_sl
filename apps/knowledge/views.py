from django.db.models import Q
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.permissions import get_employee_profile, is_erp_admin

from .models import (
    ArticleReadLog,
    KnowledgeArticle,
    KnowledgeAttachment,
    KnowledgeCategory,
    KnowledgeQuestion,
    KnowledgeTest,
    KnowledgeTestAttempt,
)
from .serializers import (
    ArticleReadLogSerializer,
    KnowledgeArticleSerializer,
    KnowledgeAttachmentSerializer,
    KnowledgeCategorySerializer,
    KnowledgeQuestionSerializer,
    KnowledgeTestAttemptSerializer,
    KnowledgeTestSerializer,
)


TRUE_VALUES = {'1', 'true', 'True', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'False', 'no', 'off'}


def parse_bool(value):
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.get_fields())


def scoped_queryset(qs, user, company_field='company', office_field='office', public_field='is_public'):
    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    company_lookup = f'{company_field}__isnull'
    public_lookup = public_field if public_field and model_has_field(qs.model, public_field) else None

    if not employee:
        filters = Q(**{company_lookup: True})
        if public_lookup:
            filters &= Q(**{public_lookup: True})
        return qs.filter(filters)

    filters = Q(**{company_field: employee.company}) | Q(**{company_lookup: True})
    if office_field and model_has_field(qs.model, office_field) and employee.office_id:
        filters &= Q(**{office_field: employee.office}) | Q(**{f'{office_field}__isnull': True})
    if public_lookup:
        filters &= Q(**{public_lookup: True})
    return qs.filter(filters)


def default_company_office(user):
    employee = get_employee_profile(user)
    if not employee:
        return {}
    return {'company': employee.company, 'office': employee.office if employee.office_id else None}


def ensure_admin(user):
    if not is_erp_admin(user):
        raise PermissionDenied('Only administrators can perform this action.')


def apply_filters(qs, request, search_fields=(), date_field='created_at'):
    company = request.query_params.get('company')
    if company and model_has_field(qs.model, 'company'):
        qs = qs.filter(company_id=company)

    office = request.query_params.get('office')
    if office and model_has_field(qs.model, 'office'):
        qs = qs.filter(office_id=office)

    category = request.query_params.get('category')
    if category and model_has_field(qs.model, 'category'):
        qs = qs.filter(category_id=category)

    article = request.query_params.get('article')
    if article and model_has_field(qs.model, 'article'):
        qs = qs.filter(article_id=article)

    test = request.query_params.get('test')
    if test and model_has_field(qs.model, 'test'):
        qs = qs.filter(test_id=test)

    status_value = request.query_params.get('status')
    if status_value and model_has_field(qs.model, 'status'):
        qs = qs.filter(status=status_value)

    for bool_field in ('is_active', 'is_public', 'is_featured', 'is_required', 'is_passed'):
        bool_value = parse_bool(request.query_params.get(bool_field))
        if bool_value is not None and model_has_field(qs.model, bool_field):
            qs = qs.filter(**{bool_field: bool_value})

    date_from = request.query_params.get('date_from')
    if date_from and date_field and model_has_field(qs.model, date_field):
        qs = qs.filter(**{f'{date_field}__gte': date_from})

    date_to = request.query_params.get('date_to')
    if date_to and date_field and model_has_field(qs.model, date_field):
        qs = qs.filter(**{f'{date_field}__lte': date_to})

    search = request.query_params.get('search')
    if search and search_fields:
        query = Q()
        for field in search_fields:
            query |= Q(**{f'{field}__icontains': search})
        qs = qs.filter(query)
    return qs


class KnowledgeCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = KnowledgeCategory.objects.select_related('company', 'parent', 'created_by')
        qs = scoped_queryset(qs, self.request.user, office_field=None)
        if not is_erp_admin(self.request.user):
            qs = qs.filter(is_active=True)
        qs = apply_filters(qs, self.request, search_fields=('name', 'code', 'description', 'company__name'))
        parent = self.request.query_params.get('parent')
        if parent:
            qs = qs.filter(parent_id=parent)
        return qs.order_by('sort_order', 'name')

    def perform_create(self, serializer):
        data = {'created_by': self.request.user}
        if not is_erp_admin(self.request.user) and not serializer.validated_data.get('company'):
            defaults = default_company_office(self.request.user)
            if defaults.get('company'):
                data['company'] = defaults['company']
        serializer.save(**data)


class KnowledgeArticleViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeArticleSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        qs = KnowledgeArticle.objects.select_related('company', 'office', 'category', 'author', 'updated_by').prefetch_related(
            'attachments',
            'tests',
            'tests__questions',
        )
        qs = scoped_queryset(qs, self.request.user)
        if not is_erp_admin(self.request.user):
            qs = qs.filter(is_active=True, status=KnowledgeArticle.STATUS_PUBLISHED)
        qs = apply_filters(
            qs,
            self.request,
            search_fields=('title', 'slug', 'summary', 'content', 'category__name', 'tags'),
            date_field='published_at',
        )
        return qs.distinct().order_by('-is_featured', '-published_at', '-updated_at')

    def perform_create(self, serializer):
        data = {'author': self.request.user, 'updated_by': self.request.user}
        if not is_erp_admin(self.request.user):
            defaults = default_company_office(self.request.user)
            if defaults.get('company') and not serializer.validated_data.get('company'):
                data['company'] = defaults['company']
            if defaults.get('office') and not serializer.validated_data.get('office'):
                data['office'] = defaults['office']
        serializer.save(**data)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        article = self.get_object()
        log = article.mark_read(request.user)
        return Response(ArticleReadLogSerializer(log, context={'request': request}).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        ensure_admin(request.user)
        article = self.get_object()
        article.publish(user=request.user)
        return Response(self.get_serializer(article).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='archive')
    def archive(self, request, pk=None):
        ensure_admin(request.user)
        article = self.get_object()
        article.archive(user=request.user)
        return Response(self.get_serializer(article).data, status=status.HTTP_200_OK)


class KnowledgeAttachmentViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeAttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_queryset(self):
        articles = scoped_queryset(KnowledgeArticle.objects.all(), self.request.user)
        if not is_erp_admin(self.request.user):
            articles = articles.filter(is_active=True, status=KnowledgeArticle.STATUS_PUBLISHED)
        article_ids = articles.values('id')
        qs = KnowledgeAttachment.objects.select_related('article', 'uploaded_by', 'article__company', 'article__office').filter(article_id__in=article_ids)
        qs = apply_filters(qs, self.request, search_fields=('title', 'url', 'note', 'article__title'))
        attachment_type = self.request.query_params.get('attachment_type')
        if attachment_type:
            qs = qs.filter(attachment_type=attachment_type)
        return qs.order_by('article__title', 'sort_order', 'created_at')

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class KnowledgeTestViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeTestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = KnowledgeTest.objects.select_related('company', 'office', 'article', 'created_by').prefetch_related('questions')
        qs = scoped_queryset(qs, self.request.user)
        if not is_erp_admin(self.request.user):
            qs = qs.filter(is_active=True)
        qs = apply_filters(qs, self.request, search_fields=('title', 'description', 'article__title', 'company__name'))
        return qs.distinct().order_by('title')

    def perform_create(self, serializer):
        data = {'created_by': self.request.user}
        if not is_erp_admin(self.request.user):
            defaults = default_company_office(self.request.user)
            if defaults.get('company') and not serializer.validated_data.get('company'):
                data['company'] = defaults['company']
            if defaults.get('office') and not serializer.validated_data.get('office'):
                data['office'] = defaults['office']
        serializer.save(**data)

    @action(detail=True, methods=['post'], url_path='start')
    def start(self, request, pk=None):
        test = self.get_object()
        if not test.can_user_start(request.user):
            raise ValidationError({'detail': 'Maximum attempts reached.'})
        attempt = KnowledgeTestAttempt.objects.create(test=test, user=request.user)
        return Response(KnowledgeTestAttemptSerializer(attempt, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        test = self.get_object()
        answers = request.data.get('answers') or {}
        attempt_id = request.data.get('attempt')
        if attempt_id:
            attempt = KnowledgeTestAttempt.objects.filter(pk=attempt_id, test=test, user=request.user).first()
            if not attempt:
                raise ValidationError({'attempt': 'Attempt not found.'})
        else:
            if not test.can_user_start(request.user):
                raise ValidationError({'detail': 'Maximum attempts reached.'})
            attempt = KnowledgeTestAttempt.objects.create(test=test, user=request.user)
        attempt.submit(answers=answers)
        return Response(KnowledgeTestAttemptSerializer(attempt, context={'request': request}).data, status=status.HTTP_200_OK)


class KnowledgeQuestionViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tests = scoped_queryset(KnowledgeTest.objects.all(), self.request.user)
        if not is_erp_admin(self.request.user):
            tests = tests.filter(is_active=True)
        test_ids = tests.values('id')
        qs = KnowledgeQuestion.objects.select_related('test').filter(test_id__in=test_ids)
        if not is_erp_admin(self.request.user):
            qs = qs.filter(is_active=True)
        qs = apply_filters(qs, self.request, search_fields=('question_text', 'test__title'))
        question_type = self.request.query_params.get('question_type')
        if question_type:
            qs = qs.filter(question_type=question_type)
        return qs.order_by('test__title', 'sort_order', 'id')


class KnowledgeTestAttemptViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeTestAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = KnowledgeTestAttempt.objects.select_related('test', 'user', 'test__company', 'test__office')
        if not is_erp_admin(self.request.user):
            qs = qs.filter(user=self.request.user)
        else:
            qs = scoped_queryset(qs, self.request.user, company_field='test__company', office_field='test__office', public_field=None)
        qs = apply_filters(qs, self.request, search_fields=('test__title', 'user__email', 'user__first_name', 'user__last_name'))
        user = self.request.query_params.get('user')
        if user and is_erp_admin(self.request.user):
            qs = qs.filter(user_id=user)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        attempt = self.get_object()
        attempt.submit(answers=request.data.get('answers') or attempt.answers)
        return Response(self.get_serializer(attempt).data, status=status.HTTP_200_OK)


class ArticleReadLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ArticleReadLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ArticleReadLog.objects.select_related('article', 'user', 'article__company', 'article__office')
        if not is_erp_admin(self.request.user):
            qs = qs.filter(user=self.request.user)
        else:
            qs = scoped_queryset(qs, self.request.user, company_field='article__company', office_field='article__office', public_field=None)
        qs = apply_filters(qs, self.request, search_fields=('article__title', 'user__email', 'user__first_name', 'user__last_name'), date_field='last_read_at')
        article = self.request.query_params.get('article')
        if article:
            qs = qs.filter(article_id=article)
        user = self.request.query_params.get('user')
        if user and is_erp_admin(self.request.user):
            qs = qs.filter(user_id=user)
        return qs.order_by('-last_read_at')
