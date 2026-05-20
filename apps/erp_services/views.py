from django.db.models import Q
from rest_framework import permissions, viewsets

from apps.core.permissions import get_employee_profile, is_erp_admin

from .models import Service, ServiceCategory, ServicePrice
from .serializers import ServiceCategorySerializer, ServicePriceSerializer, ServiceSerializer


TRUE_VALUES = {'1', 'true', 'True', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'False', 'no', 'off'}


def parse_bool(value):
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


def filter_company_or_global(queryset, user, company_field='company'):
    if is_erp_admin(user):
        return queryset

    employee = get_employee_profile(user)
    if not employee:
        return queryset.filter(**{f'{company_field}__isnull': True})

    return queryset.filter(Q(**{company_field: employee.company}) | Q(**{f'{company_field}__isnull': True}))


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ServiceCategory.objects.select_related('company')
        qs = filter_company_or_global(qs, self.request.user)

        company = self.request.query_params.get('company')
        if company:
            qs = qs.filter(company_id=company)

        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search) | Q(description__icontains=search))

        return qs.order_by('sort_order', 'name')

    def perform_create(self, serializer):
        user = self.request.user
        if is_erp_admin(user) or serializer.validated_data.get('company'):
            serializer.save()
            return

        employee = get_employee_profile(user)
        serializer.save(company=employee.company if employee else None)


class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Service.objects.select_related('company', 'category', 'currency').prefetch_related('prices')
        qs = filter_company_or_global(qs, self.request.user)

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category_id=category)

        company = self.request.query_params.get('company')
        if company:
            qs = qs.filter(company_id=company)

        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        is_public = parse_bool(self.request.query_params.get('is_public'))
        if is_public is not None:
            qs = qs.filter(is_public=is_public)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(code__icontains=search)
                | Q(description__icontains=search)
                | Q(category__name__icontains=search)
            )

        return qs.order_by('category__sort_order', 'sort_order', 'title')

    def perform_create(self, serializer):
        user = self.request.user
        if is_erp_admin(user) or serializer.validated_data.get('company'):
            serializer.save()
            return

        employee = get_employee_profile(user)
        serializer.save(company=employee.company if employee else None)


class ServicePriceViewSet(viewsets.ModelViewSet):
    serializer_class = ServicePriceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ServicePrice.objects.select_related('service', 'service__company', 'service__category', 'currency')
        qs = filter_company_or_global(qs, self.request.user, company_field='service__company')

        service = self.request.query_params.get('service')
        if service:
            qs = qs.filter(service_id=service)

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(service__category_id=category)

        company = self.request.query_params.get('company')
        if company:
            qs = qs.filter(service__company_id=company)

        is_active = parse_bool(self.request.query_params.get('is_active'))
        if is_active is not None:
            qs = qs.filter(service__is_active=is_active)

        is_public = parse_bool(self.request.query_params.get('is_public'))
        if is_public is not None:
            qs = qs.filter(service__is_public=is_public)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(service__title__icontains=search)
                | Q(service__code__icontains=search)
                | Q(currency__code__icontains=search)
                | Q(notes__icontains=search)
            )

        return qs.order_by('service__title', '-valid_from', 'currency__code')

