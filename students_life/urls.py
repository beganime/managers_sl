from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from rest_framework_simplejwt.views import TokenRefreshView

from users.auth_views import LoginView, LogoutView
from students_life.api_views import HealthCheckView, AppConfigView, DashboardSummaryView


@login_required
def my_profile_redirect(request):
    return redirect(f'/admin/users/user/{request.user.id}/change/')


urlpatterns = [
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    path('admin/profile/', my_profile_redirect, name='my_profile'),

    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
    path('privacy.html', RedirectView.as_view(url='/privacy/', permanent=True)),

    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'logo.ico', permanent=True)),
    path('', include('pwa.urls')),

    path('api/health/', HealthCheckView.as_view(), name='api_health'),
    path('api/app/config/', AppConfigView.as_view(), name='api_app_config'),
    path('api/app/dashboard/', DashboardSummaryView.as_view(), name='api_app_dashboard'),

    path('api/auth/login/', LoginView.as_view(), name='api_login'),
    path('api/auth/logout/', LogoutView.as_view(), name='api_logout'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path('api/clients/', include('clients.urls')),
    path('api/tasks/', include('tasks.urls')),
    path('api/', include('timetracking.urls')),
    path('api/', include('reports.urls')),
    path('api/', include('leads.urls')),
    path('api/', include('catalog.urls')),
    path('api/', include('services.urls')),
    path('api/', include('analytics.urls')),
    path('api/', include('gamification.urls')),
    path('api/', include('documents.urls')),
    path('api/', include('users.urls')),
    path('api/', include('notifications.urls')),
    path('api/', include('support.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)