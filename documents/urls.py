# documents/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InfoSnippetViewSet, ContractTemplateViewSet, ContractViewSet

router = DefaultRouter()
router.register(r'snippets', InfoSnippetViewSet, basename='snippet')
router.register(r'templates', ContractTemplateViewSet, basename='template')
router.register(r'contracts', ContractViewSet, basename='contract')

urlpatterns = [
    path('api/documents/', include(router.urls)),
]