# leads/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeadCreateAPIView, LeadViewSet, MobileClientDocumentSyncAPIView, MobileClientDocumentUploadAPIView, MobileClientQuestionnaireSyncAPIView, MobileClientSyncAPIView

# Используем роутер для мобильного ViewSet
router = DefaultRouter()
# Регистрируем с префиксом 'mobile', чтобы путь был /api/leads/mobile/
router.register(r'mobile', LeadViewSet, basename='lead-mobile')

urlpatterns = [
    # Эндпоинт для сайта
    path('leads/create/', LeadCreateAPIView.as_view(), name='lead-create'),
    path('mobile/clients/sync/', MobileClientSyncAPIView.as_view(), name='mobile-client-sync'),
    path('mobile/documents/sync/', MobileClientDocumentSyncAPIView.as_view(), name='mobile-document-sync'),
    path('mobile/documents/upload/', MobileClientDocumentUploadAPIView.as_view(), name='mobile-document-upload'),
    path('mobile/questionnaires/sync/', MobileClientQuestionnaireSyncAPIView.as_view(), name='mobile-questionnaire-sync'),
    # Эндпоинты для мобильного приложения
    path('leads/', include(router.urls)),
]
