from django.db.models import Prefetch, Q
from rest_framework.response import Response
from rest_framework import permissions, viewsets

from apps.education.cache import EDUCATION_CACHE_TTL, education_cache_get, education_cache_set, make_education_cache_key
from apps.education.models import City, Country, Intake, Program, ProgramFee, RequiredDocument, University
from apps.erp_services.models import Service

from .serializers import (
    ClientCitySerializer,
    ClientCountrySerializer,
    ClientProgramSerializer,
    ClientServiceSerializer,
    ClientUniversitySerializer,
)


def false_requested(value):
    return value in {'0', 'false', 'False', 'no', 'off'}


def filter_id_or_name(qs, value, id_field, name_field):
    if not value:
        return qs
    if str(value).isdigit():
        return qs.filter(**{id_field: value})
    return qs.filter(**{f'{name_field}__icontains': value})


class ClientReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]

    cache_namespace = ''

    def cache_response(self, namespace, builder):
        key = make_education_cache_key(namespace, self.request, scope='client-api', extra=str(self.kwargs.get(self.lookup_field, '')))
        cached = education_cache_get(key)
        if cached is not None:
            return Response(cached)
        response = builder()
        if response.status_code == 200:
            education_cache_set(key, response.data, EDUCATION_CACHE_TTL)
        return response

    def list(self, request, *args, **kwargs):
        if not self.cache_namespace:
            return super().list(request, *args, **kwargs)
        return self.cache_response(
            f'{self.cache_namespace}:list',
            lambda: viewsets.ReadOnlyModelViewSet.list(self, request, *args, **kwargs),
        )

    def retrieve(self, request, *args, **kwargs):
        if not self.cache_namespace:
            return super().retrieve(request, *args, **kwargs)
        return self.cache_response(
            f'{self.cache_namespace}:detail',
            lambda: viewsets.ReadOnlyModelViewSet.retrieve(self, request, *args, **kwargs),
        )


class ClientCountryViewSet(ClientReadOnlyViewSet):
    serializer_class = ClientCountrySerializer
    cache_namespace = 'countries'

    def get_queryset(self):
        qs = Country.objects.filter(is_active=True).order_by('sort_order', 'name')
        search = self.request.query_params.get('search') or self.request.query_params.get('q')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        if false_requested(self.request.query_params.get('is_active')):
            return qs.none()
        return qs


class ClientCityViewSet(ClientReadOnlyViewSet):
    serializer_class = ClientCitySerializer
    cache_namespace = 'cities'

    def get_queryset(self):
        qs = City.objects.select_related('country').filter(is_active=True, country__is_active=True)
        qs = filter_id_or_name(qs, self.request.query_params.get('country'), 'country_id', 'country__name')
        search = self.request.query_params.get('search') or self.request.query_params.get('q')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(country__name__icontains=search))
        if false_requested(self.request.query_params.get('is_active')):
            return qs.none()
        return qs.order_by('country__name', 'sort_order', 'name')


class ClientUniversityViewSet(ClientReadOnlyViewSet):
    serializer_class = ClientUniversitySerializer
    cache_namespace = 'universities'

    def get_queryset(self):
        active_programs = Program.objects.filter(is_active=True, is_archived=False).prefetch_related(
            Prefetch('fees', queryset=ProgramFee.objects.select_related('currency').order_by('-created_at', '-id')),
            Prefetch('intakes', queryset=Intake.objects.filter(is_active=True).order_by('start_date')),
            Prefetch('required_documents', queryset=RequiredDocument.objects.filter(is_active=True).order_by('sort_order', 'title')),
        )
        qs = University.objects.select_related('country', 'city').prefetch_related(
            Prefetch('programs', queryset=active_programs),
            Prefetch('required_documents', queryset=RequiredDocument.objects.filter(is_active=True).order_by('sort_order', 'title')),
        ).filter(is_active=True, country__is_active=True)
        qs = filter_id_or_name(qs, self.request.query_params.get('country'), 'country_id', 'country__name')
        qs = filter_id_or_name(qs, self.request.query_params.get('city'), 'city_id', 'city__name')
        search = self.request.query_params.get('search') or self.request.query_params.get('q')
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(country__name__icontains=search)
                | Q(city__name__icontains=search)
                | Q(description__icontains=search)
            )
        if false_requested(self.request.query_params.get('is_active')):
            return qs.none()
        return qs.distinct().order_by('country__name', 'city__name', 'name')


class ClientProgramViewSet(ClientReadOnlyViewSet):
    serializer_class = ClientProgramSerializer
    cache_namespace = 'programs'

    def get_queryset(self):
        qs = Program.objects.select_related('university', 'university__country', 'university__city').prefetch_related(
            Prefetch('fees', queryset=ProgramFee.objects.select_related('currency').order_by('-created_at', '-id')),
            Prefetch('intakes', queryset=Intake.objects.filter(is_active=True).order_by('start_date')),
            Prefetch('required_documents', queryset=RequiredDocument.objects.filter(is_active=True).order_by('sort_order', 'title')),
        ).filter(is_active=True, is_archived=False, university__is_active=True, university__country__is_active=True)
        params = self.request.query_params
        qs = filter_id_or_name(qs, params.get('country'), 'university__country_id', 'university__country__name')
        qs = filter_id_or_name(qs, params.get('city'), 'university__city_id', 'university__city__name')
        qs = filter_id_or_name(qs, params.get('university'), 'university_id', 'university__name')
        if params.get('degree'):
            qs = qs.filter(degree=params['degree'])
        if params.get('language'):
            qs = qs.filter(language__icontains=params['language'])
        search = params.get('search') or params.get('q')
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(faculty__icontains=search)
                | Q(language__icontains=search)
                | Q(university__name__icontains=search)
                | Q(university__country__name__icontains=search)
            )
        if false_requested(params.get('is_active')):
            return qs.none()
        return qs.distinct().order_by('university__name', 'degree', 'name')


class ClientServiceViewSet(ClientReadOnlyViewSet):
    serializer_class = ClientServiceSerializer

    def get_queryset(self):
        qs = Service.objects.select_related('category', 'currency').filter(is_active=True, is_public=True)
        params = self.request.query_params
        if params.get('category'):
            qs = filter_id_or_name(qs, params.get('category'), 'category_id', 'category__name')
        search = params.get('search') or params.get('q')
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search) | Q(category__name__icontains=search))
        if false_requested(params.get('is_active')):
            return qs.none()
        return qs.order_by('category__sort_order', 'sort_order', 'title')
