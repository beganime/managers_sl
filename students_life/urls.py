from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    # Главная страница -> Сразу в админку
    path('', RedirectView.as_view(url='/admin/', permanent=False)),
    
    path('admin/', admin.site.urls),
    
    # Пути для PWA (manifest.json, service-worker)
    path('', include('pwa.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)