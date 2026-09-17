from django.urls import path

from .views import PublicOnboardingSubmissionCreateView, PublicOnboardingSubmissionDetailView


urlpatterns = [
    path('submissions/', PublicOnboardingSubmissionCreateView.as_view(), name='client-onboarding-create'),
    path(
        'submissions/<uuid:public_id>/',
        PublicOnboardingSubmissionDetailView.as_view(),
        name='client-onboarding-detail',
    ),
]
