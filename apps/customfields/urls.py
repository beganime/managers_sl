from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CustomFieldOptionViewSet, CustomFieldValueViewSet, CustomFieldViewSet

router = DefaultRouter()
router.register('fields', CustomFieldViewSet, basename='custom-field')
router.register('options', CustomFieldOptionViewSet, basename='custom-field-option')
router.register('values', CustomFieldValueViewSet, basename='custom-field-value')

urlpatterns = [
    path('', include(router.urls)),
]
