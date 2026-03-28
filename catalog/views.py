from django.db.models import Count, Q
from django.utils.dateparse import parse_datetime
from rest_framework import filters, permissions, viewsets

from .models import Currency, University, Program
from .pagination import ProgramPagination, UniversityPagination
from .serializers import (
    CurrencySerializer,
    ProgramSerializer,
    UniversityDetailSerializer,
    UniversityListSerializer,
)


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CurrencySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Currency.objects.all()
        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)
        return qs.order_by('-updated_at')


class UniversityViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = UniversityPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'country', 'city']

    def get_queryset(self):
        qs = (
            University.objects
            .select_related('local_currency')
            .annotate(
                programs_count=Count(
                    'programs',
                    filter=Q(programs__is_deleted=False, programs__is_active=True)
                )
            )
            .all()
        )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        country = self.request.query_params.get('country')
        if country and country != 'all':
            qs = qs.filter(country=country)

        return qs.order_by('name')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UniversityDetailSerializer
        return UniversityListSerializer


class ProgramViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProgramSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ProgramPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'degree', 'university__name', 'university__country', 'university__city']

    def get_queryset(self):
        qs = (
            Program.objects
            .select_related('university', 'university__local_currency')
            .filter(is_deleted=False, is_active=True)
        )

        updated_after = self.request.query_params.get('updated_after')
        if updated_after:
            dt = parse_datetime(updated_after)
            if dt:
                qs = qs.filter(updated_at__gte=dt)

        country = self.request.query_params.get('country')
        if country and country != 'all':
            qs = qs.filter(university__country=country)

        university_id = self.request.query_params.get('university')
        if university_id:
            qs = qs.filter(university_id=university_id)

        degree = self.request.query_params.get('degree')
        if degree:
            qs = qs.filter(degree=degree)

        max_price = self.request.query_params.get('max_price')
        if max_price:
            try:
                qs = qs.filter(tuition_fee__lte=max_price)
            except Exception:
                pass

        sort = self.request.query_params.get('sort')
        if sort == 'price_asc':
            qs = qs.order_by('tuition_fee', 'name')
        elif sort == 'price_desc':
            qs = qs.order_by('-tuition_fee', 'name')
        else:
            qs = qs.order_by('name')

        return qs