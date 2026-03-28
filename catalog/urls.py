from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CurrencyViewSet, UniversityViewSet, ProgramViewSet

router = DefaultRouter()
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'universities', UniversityViewSet, basename='university')
router.register(r'programs', ProgramViewSet, basename='program')

urlpatterns = [
    path('catalog/', include(router.urls)),
]