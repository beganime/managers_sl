# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, OfficeViewSet

router = DefaultRouter()
router.register(r'offices', OfficeViewSet, basename='office')
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    path('users/', include(router.urls)),
]