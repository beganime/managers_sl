from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SupportMessageViewSet

router = DefaultRouter()
router.register(r'messages', SupportMessageViewSet, basename='support-message')

urlpatterns = [
    path('support/', include(router.urls)),
]