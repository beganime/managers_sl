from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AttendanceReminderViewSet, AutoCloseLogViewSet, DailyReportViewSet, WorkDayViewSet

router = DefaultRouter()
router.register('workdays', WorkDayViewSet, basename='attendance-workday')
router.register('reports', DailyReportViewSet, basename='attendance-report')
router.register('reminders', AttendanceReminderViewSet, basename='attendance-reminder')
router.register('auto-close-logs', AutoCloseLogViewSet, basename='attendance-auto-close-log')

urlpatterns = [
    path('', include(router.urls)),
]
