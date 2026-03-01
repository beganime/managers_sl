# catalog/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CurrencyViewSet, UniversityViewSet

router = DefaultRouter()
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'universities', UniversityViewSet, basename='university')

urlpatterns = [
    path('catalog/', include(router.urls)),
]