from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError

from apps.core.permissions import get_employee_profile, is_erp_admin

from .models import CustomField, CustomFieldOption, CustomFieldValue
from .serializers import CustomFieldOptionSerializer, CustomFieldSerializer, CustomFieldValueSerializer


TRUE_VALUES = {'1', 'true', 'True', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'False', 'no', 'off'}


def parse_bool(value):
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


def default_company_office(user):
    employee = get_employee_profile(user)
    if not employee:
        return {}
    return {'company': employee.company, 'office': employee.office if employee.office_id else None}


def parse_content_type(value):
    if not value:
        return None
    if str(value).isdigit():
        return ContentType.objects.filter(pk=value).first()
    if '.' in str(value):
        app_label, model = str(value).split('.', 1)
        return ContentType.objects.filter(app_label=app_label, model=model.lower()).first()
    return None


def field_scope(qs, user):
    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(company__isnull=True, is_public=True)

    filters = Q(company=employee.company) | Q(company__isnull=True)
    if employee.office_id:
        filters &= Q(office=employee.office) | Q(office__isnull=True)
    return qs.filter(filters, is_public=True)


def value_scope(qs, user):
    if is_erp_admin(user):
        return qs

    employee = get_employee_profile(user)
    if not employee:
        return qs.filter(Q(company__isnull=True), field__is_public=True)

    filters = Q(company=employee.company) | Q(company__isnull=True)
    field_filters = Q(field__company=employee.company) | Q(field__company__isnull=True)
    if employee.office_id:
        filters &= Q(office=employee.office) | Q(office__isnull=True)
        field_filters &= Q(field__office=employee.office) | Q(field__office__isnull=True)
    return qs.filter(filters, field_filters, field__is_public=True)


def apply_field_filters(qs, request):
    company = request.query_params.get('company')
    if company:
        qs = qs.filter(company_id=company)

    office = request.query_params.get('office')
    if office:
        qs = qs.filter(office_id=office)

    content_type = parse_content_type(request.query_params.get('content_type') or request.query_params.get('model'))
    if content_type:
        qs = qs.filter(content_type=content_type)

    entity_key = request.query_params.get('entity_key')
    if entity_key:
        qs = qs.filter(entity_key=entity_key)

    field_type = request.query_params.get('field_type')
    if field_type:
        qs = qs.filter(field_type=field_type)

    for bool_field in ('is_active', 'is_required', 'is_filterable', 'is_public'):
        bool_value = parse_bool(request.query_params.get(bool_field))
        if bool_value is not None:
            qs = qs.filter(**{bool_field: bool_value})

    search = request.query_params.get('search')
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search) | Q(description__icontains=search) | Q(entity_key__icontains=search))
    return qs


class CustomFieldViewSet(viewsets.ModelViewSet):
    serializer_class = CustomFieldSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = CustomField.objects.select_related('company', 'office', 'content_type', 'created_by').prefetch_related('options')
        qs = field_scope(qs, self.request.user)
        return apply_field_filters(qs, self.request).order_by('sort_order', 'name')

    def perform_create(self, serializer):
        data = {'created_by': self.request.user}
        if not is_erp_admin(self.request.user):
            defaults = default_company_office(self.request.user)
            if defaults.get('company') and not serializer.validated_data.get('company'):
                data['company'] = defaults['company']
            if defaults.get('office') and not serializer.validated_data.get('office'):
                data['office'] = defaults['office']
        serializer.save(**data)


class CustomFieldOptionViewSet(viewsets.ModelViewSet):
    serializer_class = CustomFieldOptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        field_ids = field_scope(CustomField.objects.all(), self.request.user).values('id')
        qs = CustomFieldOption.objects.select_related('field').filter(field_id__in=field_ids)

        field = self.request.query_params.get('field')
        if field:
            qs = qs.filter(field_id=field)

        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(label__icontains=search) | Q(value__icontains=search) | Q(field__name__icontains=search))

        return qs.order_by('field__sort_order', 'field__name', 'sort_order', 'label')


class CustomFieldValueViewSet(viewsets.ModelViewSet):
    serializer_class = CustomFieldValueSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = CustomFieldValue.objects.select_related('field', 'company', 'office', 'content_type', 'set_by')
        qs = value_scope(qs, self.request.user)

        field = self.request.query_params.get('field')
        if field:
            qs = qs.filter(field_id=field)

        company = self.request.query_params.get('company')
        if company:
            qs = qs.filter(company_id=company)

        office = self.request.query_params.get('office')
        if office:
            qs = qs.filter(office_id=office)

        content_type = parse_content_type(self.request.query_params.get('content_type') or self.request.query_params.get('model'))
        if content_type:
            qs = qs.filter(content_type=content_type)

        object_id = self.request.query_params.get('object_id')
        if object_id:
            qs = qs.filter(object_id=object_id)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(value_search__icontains=search) | Q(field__name__icontains=search) | Q(field__code__icontains=search))

        return qs.order_by('field__sort_order', 'field__name')

    def perform_create(self, serializer):
        field = serializer.validated_data.get('field')
        content_type = serializer.validated_data.get('content_type')
        object_id = serializer.validated_data.get('object_id')
        model_class = content_type.model_class()
        if model_class is None or not model_class._default_manager.filter(pk=object_id).exists():
            raise ValidationError({'object_id': 'Object does not exist for selected content type.'})

        data = {'set_by': self.request.user}
        if not serializer.validated_data.get('company') and field.company_id:
            data['company'] = field.company
        if not serializer.validated_data.get('office') and field.office_id:
            data['office'] = field.office
        if not is_erp_admin(self.request.user):
            defaults = default_company_office(self.request.user)
            if defaults.get('company') and not serializer.validated_data.get('company') and not data.get('company'):
                data['company'] = defaults['company']
            if defaults.get('office') and not serializer.validated_data.get('office') and not data.get('office'):
                data['office'] = defaults['office']
        serializer.save(**data)

    def perform_update(self, serializer):
        serializer.save(set_by=self.request.user)
