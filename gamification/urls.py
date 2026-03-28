# gamification/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, LeaderboardViewSet, TutorialVideoViewSet

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'tutorials', TutorialVideoViewSet, basename='tutorial')
router.register(r'leaderboard', LeaderboardViewSet, basename='leaderboard')

urlpatterns = [
    path('gamification/', include(router.urls)),
]