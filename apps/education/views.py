from django.db.models import Q
from rest_framework import permissions, viewsets

from .models import City, Country, Currency, Intake, Program, ProgramFee, RequiredDocument, University, UniversityContact
from .serializers import (
    CitySerializer,
    CountrySerializer,
    CurrencySerializer,
    IntakeSerializer,
    ProgramFeeSerializer,
    ProgramSerializer,
    RequiredDocumentSerializer,
    UniversityContactSerializer,
    UniversityDetailSerializer,
    UniversitySerializer,
)


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all().order_by('sort_order', 'name')
    serializer_class = CountrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs


class CityViewSet(viewsets.ModelViewSet):
    serializer_class = CitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = City.objects.select_related('country').all().order_by('country__name', 'sort_order', 'name')
        country = self.request.query_params.get('country')
        if country:
            qs = qs.filter(country_id=country)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(country__name__icontains=search))
        return qs


class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all().order_by('code')
    serializer_class = CurrencySerializer
    permission_classes = [permissions.IsAuthenticated]


class UniversityViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UniversityDetailSerializer
        return UniversitySerializer

    def get_queryset(self):
        qs = University.objects.select_related('company', 'country', 'city', 'local_currency', 'added_by').prefetch_related(
            'programs', 'contact_people', 'required_documents'
        )
        country = self.request.query_params.get('country')
        if country:
            qs = qs.filter(country_id=country)
        city = self.request.query_params.get('city')
        if city:
            qs = qs.filter(city_id=city)
        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(country__name__icontains=search)
                | Q(city__name__icontains=search)
                | Q(description__icontains=search)
            )
        return qs.order_by('country__name', 'city__name', 'name')

    def perform_create(self, serializer):
        serializer.save(added_by=self.request.user)


class ProgramViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Program.objects.select_related('university', 'university__country', 'university__city').prefetch_related(
            'fees', 'intakes', 'required_documents'
        )
        university = self.request.query_params.get('university')
        if university:
            qs = qs.filter(university_id=university)
        country = self.request.query_params.get('country')
        if country:
            qs = qs.filter(university__country_id=country)
        degree = self.request.query_params.get('degree')
        if degree:
            qs = qs.filter(degree=degree)
        language = self.request.query_params.get('language')
        if language:
            qs = qs.filter(language__icontains=language)
        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True, is_archived=False)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(faculty__icontains=search)
                | Q(university__name__icontains=search)
                | Q(university__country__name__icontains=search)
            )
        return qs.order_by('university__name', 'degree', 'name')


class ProgramFeeViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramFeeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ProgramFee.objects.select_related('program', 'program__university', 'currency')
        program = self.request.query_params.get('program')
        if program:
            qs = qs.filter(program_id=program)
        return qs.order_by('program__university__name', 'program__name', '-valid_from')


class IntakeViewSet(viewsets.ModelViewSet):
    serializer_class = IntakeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Intake.objects.select_related('program', 'program__university')
        program = self.request.query_params.get('program')
        if program:
            qs = qs.filter(program_id=program)
        is_active = self.request.query_params.get('is_active')
        if is_active in ('1', 'true', 'True'):
            qs = qs.filter(is_active=True)
        return qs.order_by('start_date', 'title')


class RequiredDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = RequiredDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = RequiredDocument.objects.select_related('university', 'program')
        university = self.request.query_params.get('university')
        if university:
            qs = qs.filter(university_id=university)
        program = self.request.query_params.get('program')
        if program:
            qs = qs.filter(program_id=program)
        return qs.order_by('sort_order', 'title')


class UniversityContactViewSet(viewsets.ModelViewSet):
    serializer_class = UniversityContactSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = UniversityContact.objects.select_related('university', 'university__country')
        university = self.request.query_params.get('university')
        if university:
            qs = qs.filter(university_id=university)
        return qs.order_by('university__name', 'full_name')
