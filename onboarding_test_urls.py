from django.urls import include, path

urlpatterns = [
    path('api/client/v1/onboarding/', include('apps.client_onboarding.public_urls')),
    path('api/v1/onboarding/', include('apps.client_onboarding.manager_urls')),
]
