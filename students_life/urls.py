from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from rest_framework_simplejwt.views import TokenRefreshView

from apps.portal.views import PortalHomeView
from users.auth_views import LoginView, LogoutView
from students_life.api_views import HealthCheckView, AppConfigView, DashboardSummaryView
from students_life.mobile_api import (
    CalendarEventDetailView,
    CalendarEventListCreateView,
    DashboardView as MobileDashboardView,
    MeView,
    MobileBootstrapView,
    MobileSearchView,
    RatingView as MobileRatingView,
)


@login_required
def my_profile_redirect(request):
    return redirect(f'/admin/users/user/{request.user.id}/change/')


urlpatterns = [
    path('', PortalHomeView.as_view(), name='home'),
    path('admin/profile/', my_profile_redirect, name='my_profile'),

    path('privacy/', TemplateView.as_view(template_name='privacy.html'), name='privacy'),
    path('privacy.html', RedirectView.as_view(url='/privacy/', permanent=True)),

    path('portal/', include('apps.portal.urls')),
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'logo.ico', permanent=True)),
    path('', include('pwa.urls')),

    path('api/health/', HealthCheckView.as_view(), name='api_health'),
    path('api/app/config/', AppConfigView.as_view(), name='api_app_config'),
    path('api/app/dashboard/', DashboardSummaryView.as_view(), name='api_app_dashboard'),

    path('api/v1/me/', MeView.as_view(), name='api_v1_me'),
    path('api/v1/dashboard/', MobileDashboardView.as_view(), name='api_v1_dashboard'),
    path('api/v1/calendar/events/', CalendarEventListCreateView.as_view(), name='api_v1_calendar_events'),
    path('api/v1/calendar/events/<int:pk>/', CalendarEventDetailView.as_view(), name='api_v1_calendar_event_detail'),
    path('api/v1/mobile/bootstrap/', MobileBootstrapView.as_view(), name='api_v1_mobile_bootstrap'),
    path('api/v1/mobile/search/', MobileSearchView.as_view(), name='api_v1_mobile_search'),
    path('api/v1/rating/', MobileRatingView.as_view(), name='api_v1_rating'),

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

    path('api/v1/crm/', include('apps.crm.urls')),
    path('api/v1/education/', include('apps.education.urls')),
    path('api/v1/services/', include('apps.erp_services.urls')),
    path('api/v1/finance/', include('apps.finance.urls')),
    path('api/v1/documents/', include('apps.erp_documents.urls')),
    path('api/v1/attendance/', include('apps.attendance.urls')),
    path('api/v1/projects/', include('apps.projects_v2.urls')),
    path('api/v1/knowledge/', include('apps.knowledge.urls')),
    path('api/v1/customfields/', include('apps.customfields.urls')),
    path('api/v1/notifications/', include('apps.erp_notifications.urls')),
    path('api/client/v1/', include('apps.client_api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
