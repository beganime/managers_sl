# documents/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    InfoSnippetViewSet,
    DocumentTemplateViewSet,
    GeneratedDocumentViewSet,
    KnowledgeTestViewSet,
)

router = DefaultRouter()
router.register(r'snippets', InfoSnippetViewSet, basename='snippet')
router.register(r'templates', DocumentTemplateViewSet, basename='template')
router.register(r'generated', GeneratedDocumentViewSet, basename='generateddocument')
router.register(r'knowledge-tests', KnowledgeTestViewSet, basename='knowledge-test')

urlpatterns = [
    path('documents/', include(router.urls)),
]