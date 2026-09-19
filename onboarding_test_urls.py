from django.urls import include, path

from users.disk_auth import disk_authenticate

urlpatterns = [
    path('api/internal/disk/auth/', disk_authenticate, name='disk_authenticate'),
    path('api/client/v1/onboarding/', include('apps.client_onboarding.public_urls')),
    path('api/v1/onboarding/', include('apps.client_onboarding.manager_urls')),
]
