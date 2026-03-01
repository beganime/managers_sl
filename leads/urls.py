# leads/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeadCreateAPIView, LeadViewSet

# Используем роутер для мобильного ViewSet
router = DefaultRouter()
# Регистрируем с префиксом 'mobile', чтобы путь был /api/leads/mobile/
router.register(r'mobile', LeadViewSet, basename='lead-mobile')

urlpatterns = [
    # Эндпоинт для сайта
    path('leads/create/', LeadCreateAPIView.as_view(), name='lead-create'),
    # Эндпоинты для мобильного приложения
    path('leads/', include(router.urls)),
]