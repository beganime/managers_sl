from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CityViewSet,
    CountryViewSet,
    CurrencyViewSet,
    IntakeViewSet,
    ProgramFeeViewSet,
    ProgramViewSet,
    RequiredDocumentViewSet,
    UniversityContactViewSet,
    UniversityViewSet,
)

router = DefaultRouter()
router.register('countries', CountryViewSet, basename='education-country')
router.register('cities', CityViewSet, basename='education-city')
router.register('currencies', CurrencyViewSet, basename='education-currency')
router.register('universities', UniversityViewSet, basename='education-university')
router.register('programs', ProgramViewSet, basename='education-program')
router.register('program-fees', ProgramFeeViewSet, basename='education-program-fee')
router.register('intakes', IntakeViewSet, basename='education-intake')
router.register('required-documents', RequiredDocumentViewSet, basename='education-required-document')
router.register('university-contacts', UniversityContactViewSet, basename='education-university-contact')

urlpatterns = [
    path('', include(router.urls)),
]
