from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DeviceTokenViewSet,
    NotificationViewSet,
    LeaderboardViewSet,
    PushBroadcastViewSet,
    TutorialVideoViewSet,
)

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'leaderboard', LeaderboardViewSet, basename='leaderboard')
router.register(r'device-tokens', DeviceTokenViewSet, basename='device-token')
router.register(r'push-broadcasts', PushBroadcastViewSet, basename='push-broadcast')
router.register(r'tutorials', TutorialVideoViewSet, basename='tutorial')

urlpatterns = [
    path('gamification/', include(router.urls)),
]