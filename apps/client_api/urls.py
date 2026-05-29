from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClientCityViewSet,
    ClientCountryViewSet,
    ClientProgramViewSet,
    ClientServiceViewSet,
    ClientUniversityViewSet,
)


router = DefaultRouter()
router.register('countries', ClientCountryViewSet, basename='client-country')
router.register('cities', ClientCityViewSet, basename='client-city')
router.register('universities', ClientUniversityViewSet, basename='client-university')
router.register('programs', ClientProgramViewSet, basename='client-program')
router.register('services', ClientServiceViewSet, basename='client-service')


urlpatterns = [
    path('', include(router.urls)),
]
