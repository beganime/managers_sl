# students_life/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# Функция перенаправления в свой профиль
@login_required
def my_profile_redirect(request):
    return redirect(f'/admin/users/user/{request.user.id}/change/')

urlpatterns = [
    # Главная страница -> Сразу в админку
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    
    # Ссылка на личный профиль
    path('admin/profile/', my_profile_redirect, name='my_profile'),
    
    path('admin/', admin.site.urls),
    path('favicon.ico', RedirectView.as_view(url=settings.STATIC_URL + 'logo.ico', permanent=True)),
    path('', include('leads.urls')),
    path('', include('pwa.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'), # Логин (получить токен)
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'), # Обновить токен
    
    path('api/clients/', include('clients.urls')),
    path('api/tasks/', include('tasks.urls')),
    path('', include('timetracking.urls')),
    path('', include('reports.urls')),
    path('', include('catalog.urls')),
    path('', include('services.urls')),
    path('', include('analytics.urls')),
    path('', include('gamification.urls')),
    path('', include('documents.urls')),
    path('', include('users.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)