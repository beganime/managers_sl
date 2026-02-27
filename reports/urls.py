# reports/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DailyReportViewSet

router = DefaultRouter()
router.register(r'daily', DailyReportViewSet, basename='dailyreport')

urlpatterns = [
    path('api/reports/', include(router.urls)),
]