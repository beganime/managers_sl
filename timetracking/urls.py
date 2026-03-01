# timetracking/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import WorkShiftViewSet

router = DefaultRouter()
router.register(r'shifts', WorkShiftViewSet, basename='workshift')

urlpatterns = [
    path('timetracking/', include(router.urls)),
]