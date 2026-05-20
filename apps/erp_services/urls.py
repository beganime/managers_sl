from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ServiceCategoryViewSet, ServicePriceViewSet, ServiceViewSet

router = DefaultRouter()
router.register('categories', ServiceCategoryViewSet, basename='erp-service-category')
router.register('services', ServiceViewSet, basename='erp-service')
router.register('prices', ServicePriceViewSet, basename='erp-service-price')

urlpatterns = [
    path('', include(router.urls)),
]

