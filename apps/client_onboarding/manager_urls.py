from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ManagerOnboardingSubmissionViewSet


router = DefaultRouter()
router.register('submissions', ManagerOnboardingSubmissionViewSet, basename='manager-onboarding-submission')

urlpatterns = [path('', include(router.urls))]
