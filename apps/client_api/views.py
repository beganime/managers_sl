from decimal import Decimal, InvalidOperation

from django.db.models import Count, DateField, DecimalField, OuterRef, Prefetch, Q, Subquery
from rest_framework.response import Response
from rest_framework import permissions, viewsets

from apps.education.cache import EDUCATION_CACHE_TTL, education_cache_get, education_cache_set, make_education_cache_key
from apps.education.models import City, Country, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact
from apps.erp_services.models import Service

from .serializers import (
    ClientIntakeSerializer,
    ClientCitySerializer,
    ClientCountrySerializer,
    ClientProgramFeeSerializer,
    ClientProgramSerializer,
    ClientServiceSerializer,
    ClientUniversitySerializer,
    absolute_file_url,
    decimal_to_string,
)


def false_requested(value):
    return value in {'0', 'false', 'False', 'no', 'off'}


def filter_id_or_name(qs, value, id_field, name_field):
    if not value:
        return qs
    if str(value).isdigit():
        return qs.filter(**{id_field: value})
    return qs.filter(**{f'{name_field}__icontains': value})


def decimal_param(params, name):
    value = params.get(name)
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value).replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        return None


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
        qs = Country.objects.filter(is_active=True).annotate(
            cities_count=Count('cities', filter=Q(cities__is_active=True), distinct=True),
            universities_count=Count('universities', filter=Q(universities__is_active=True), distinct=True),
        ).order_by('sort_order', 'name')
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
        qs = City.objects.select_related('country').filter(is_active=True, country__is_active=True).annotate(
            universities_count=Count('universities', filter=Q(universities__is_active=True), distinct=True),
        )
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
            Prefetch('contact_people', queryset=UniversityContact.objects.filter(is_active=True).order_by('full_name', 'id')),
        ).filter(is_active=True, country__is_active=True).annotate(
            programs_count=Count('programs', filter=Q(programs__is_active=True, programs__is_archived=False), distinct=True),
        )
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

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception:
            return self._fallback_list_from_universities(request)

    def _fallback_list_from_universities(self, request):
        params = request.query_params
        universities = University.objects.select_related('country', 'city').prefetch_related(
            Prefetch(
                'programs',
                queryset=Program.objects.filter(is_active=True, is_archived=False).prefetch_related(
                    Prefetch('fees', queryset=ProgramFee.objects.select_related('currency').order_by('-created_at', '-id')),
                    Prefetch('intakes', queryset=Intake.objects.filter(is_active=True).order_by('application_deadline', 'start_date')),
                ).order_by('name'),
            )
        ).filter(is_active=True, country__is_active=True)
        universities = filter_id_or_name(universities, params.get('country'), 'country_id', 'country__name')
        universities = filter_id_or_name(universities, params.get('city'), 'city_id', 'city__name')
        universities = filter_id_or_name(universities, params.get('university'), 'id', 'name')

        search = (params.get('search') or params.get('q') or '').strip().lower()
        level = (params.get('degree') or params.get('level') or '').strip().lower()
        language = (params.get('language') or '').strip().lower()
        price_min = decimal_param(params, 'price_min')
        price_max = decimal_param(params, 'price_max')
        rows = []

        for university in universities:
            for program in university.programs.all():
                fee = next(iter(program.fees.all()), None)
                intake = next(iter(program.intakes.all()), None)
                tuition_fee = fee.tuition_fee if fee else None
                text = ' '.join(
                    str(value or '').lower()
                    for value in (
                        program.name,
                        program.faculty,
                        program.language,
                        program.description,
                        program.admission_requirements,
                        university.name,
                        university.country.name if university.country_id else '',
                        university.city.name if university.city_id else '',
                    )
                )
                if search and search not in text:
                    continue
                if level and level not in str(program.degree or '').lower() and level not in str(program.get_degree_display()).lower():
                    continue
                if language and language not in str(program.language or '').lower():
                    continue
                if price_min is not None and tuition_fee is not None and tuition_fee < price_min:
                    continue
                if price_max is not None and tuition_fee is not None and tuition_fee > price_max:
                    continue

                rows.append({
                    'id': program.id,
                    'program_id': program.id,
                    'program_title': program.name,
                    'university': university.id,
                    'university_id': university.id,
                    'university_name': university.name,
                    'country': university.country_id,
                    'country_id': university.country_id,
                    'country_name': university.country.name if university.country_id else '',
                    'city': university.city_id,
                    'city_id': university.city_id,
                    'city_name': university.city.name if university.city_id else '',
                    'name': program.name,
                    'degree': program.degree,
                    'level': program.get_degree_display(),
                    'degree_display': program.get_degree_display(),
                    'faculty': program.faculty,
                    'language': program.language,
                    'duration': program.duration,
                    'description': program.description,
                    'admission_requirements': program.admission_requirements,
                    'tuition_fee': decimal_to_string(tuition_fee),
                    'currency': fee.currency.code if fee and fee.currency_id else '',
                    'currency_symbol': fee.currency.symbol if fee and fee.currency_id else '',
                    'converted_tuition_fee': None,
                    'selected_currency': '',
                    'application_deadline': intake.application_deadline if intake else None,
                    'fees': ClientProgramFeeSerializer([fee], many=True, context={'request': request}).data if fee else [],
                    'intakes': ClientIntakeSerializer([intake], many=True, context={'request': request}).data if intake else [],
                    'required_documents': [],
                    'university_logo': absolute_file_url(request, university.logo),
                    'university_cover': absolute_file_url(request, university.cover_image),
                })

        ordering = params.get('ordering') or ''
        if ordering == 'price_desc':
            rows.sort(key=lambda item: Decimal(item['tuition_fee'] or '0'), reverse=True)
        elif ordering in {'title_asc', 'name'}:
            rows.sort(key=lambda item: item['program_title'])
        elif ordering == 'country_asc':
            rows.sort(key=lambda item: (item['country_name'], item['city_name'], item['program_title']))
        elif ordering == 'city_asc':
            rows.sort(key=lambda item: (item['city_name'], item['country_name'], item['program_title']))
        elif ordering == 'deadline_asc':
            rows.sort(key=lambda item: (item['application_deadline'] is None, item['application_deadline'] or '9999-12-31'))
        else:
            rows.sort(key=lambda item: Decimal(item['tuition_fee'] or '0'))

        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(rows)

    def get_queryset(self):
        first_fee = ProgramFee.objects.filter(program=OuterRef('pk')).order_by('-created_at', '-id')
        first_intake = Intake.objects.filter(program=OuterRef('pk'), is_active=True).order_by('application_deadline', 'start_date', 'id')
        qs = Program.objects.select_related('university', 'university__country', 'university__city').prefetch_related(
            Prefetch('fees', queryset=ProgramFee.objects.select_related('currency').order_by('-created_at', '-id')),
            Prefetch('intakes', queryset=Intake.objects.filter(is_active=True).order_by('application_deadline', 'start_date')),
            Prefetch('required_documents', queryset=RequiredDocument.objects.filter(is_active=True).order_by('sort_order', 'title')),
        ).filter(is_active=True, is_archived=False, university__is_active=True, university__country__is_active=True).annotate(
            first_tuition_fee=Subquery(first_fee.values('tuition_fee')[:1], output_field=DecimalField(max_digits=14, decimal_places=2)),
            first_deadline=Subquery(first_intake.values('application_deadline')[:1], output_field=DateField()),
        )
        params = self.request.query_params
        qs = filter_id_or_name(qs, params.get('country'), 'university__country_id', 'university__country__name')
        qs = filter_id_or_name(qs, params.get('city'), 'university__city_id', 'university__city__name')
        qs = filter_id_or_name(qs, params.get('university'), 'university_id', 'university__name')
        degree = params.get('degree') or params.get('level')
        if degree:
            qs = qs.filter(Q(degree__iexact=degree) | Q(degree__icontains=degree))
        if params.get('language'):
            qs = qs.filter(language__icontains=params['language'])
        price_min = decimal_param(params, 'price_min')
        price_max = decimal_param(params, 'price_max')
        if price_min is not None:
            qs = qs.filter(first_tuition_fee__gte=price_min)
        if price_max is not None:
            qs = qs.filter(first_tuition_fee__lte=price_max)
        search = params.get('search') or params.get('q')
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(faculty__icontains=search)
                | Q(language__icontains=search)
                | Q(description__icontains=search)
                | Q(admission_requirements__icontains=search)
                | Q(university__name__icontains=search)
                | Q(university__country__name__icontains=search)
                | Q(university__city__name__icontains=search)
            )
        if false_requested(params.get('is_active')):
            return qs.none()
        ordering = params.get('ordering') or ''
        ordering_map = {
            'price': ('first_tuition_fee', 'name'),
            'price_asc': ('first_tuition_fee', 'name'),
            'price_desc': ('-first_tuition_fee', 'name'),
            'title_asc': ('name', 'university__name'),
            'country_asc': ('university__country__name', 'university__city__name', 'name'),
            'city_asc': ('university__city__name', 'university__country__name', 'name'),
            'deadline_asc': ('first_deadline', 'name'),
        }
        return qs.distinct().order_by(*ordering_map.get(ordering, ('university__name', 'degree', 'name')))


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
