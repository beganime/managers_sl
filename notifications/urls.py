from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FCMDeviceViewSet

router = DefaultRouter()
router.register(r'devices', FCMDeviceViewSet, basename='notification-device')

urlpatterns = [
    path('notifications/', include(router.urls)),
]