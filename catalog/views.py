from django.db.models import Case, Count, IntegerField, Q, When
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, viewsets

from .models import Currency, University, Program
from .pagination import ProgramPagination, UniversityPagination
from .search import rank_queryset_by_search
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

    def get_queryset(self):
        qs = (
            University.objects
            .select_related('local_currency')
            .annotate(
                programs_count=Count(
                    'programs',
                    filter=Q(programs__is_deleted=False, programs__is_active=True),
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

        search = (self.request.query_params.get('search') or '').strip()
        if search:
            ranked_ids = rank_queryset_by_search(
                list(qs[:500]),
                search,
                lambda obj: ' '.join(
                    filter(
                        None,
                        [
                            obj.name,
                            obj.country,
                            obj.city,
                            getattr(obj, 'description', ''),
                            getattr(obj, 'required_docs', ''),
                        ],
                    )
                ),
                min_score=0.43,
            )
            if ranked_ids:
                preserved = Case(
                    *[When(id=pk, then=pos) for pos, pk in enumerate(ranked_ids)],
                    output_field=IntegerField(),
                )
                return qs.filter(id__in=ranked_ids).order_by(preserved)

        return qs.order_by('name')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UniversityDetailSerializer
        return UniversityListSerializer


class ProgramViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProgramSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ProgramPagination

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

        search = (self.request.query_params.get('search') or '').strip()
        if search:
            ranked_ids = rank_queryset_by_search(
                list(qs[:1000]),
                search,
                lambda obj: ' '.join(
                    filter(
                        None,
                        [
                            obj.name,
                            obj.degree,
                            getattr(obj.university, 'name', ''),
                            getattr(obj.university, 'country', ''),
                            getattr(obj.university, 'city', ''),
                        ],
                    )
                ),
                min_score=0.42,
            )
            if ranked_ids:
                preserved = Case(
                    *[When(id=pk, then=pos) for pos, pk in enumerate(ranked_ids)],
                    output_field=IntegerField(),
                )
                qs = qs.filter(id__in=ranked_ids).order_by(preserved)
                return qs

        sort = self.request.query_params.get('sort')
        if sort == 'price_asc':
            return qs.order_by('tuition_fee', 'name')
        if sort == 'price_desc':
            return qs.order_by('-tuition_fee', 'name')
        return qs.order_by('name')