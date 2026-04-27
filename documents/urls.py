from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .mobile_views import GeneratedDocumentViewSet

from .views import (
    DocumentTemplateViewSet,
    InfoSnippetViewSet,
    KnowledgeSectionAttachmentViewSet,
    KnowledgeSectionViewSet,
    KnowledgeTestAttemptViewSet,
    KnowledgeTestViewSet,
)

router = DefaultRouter()
router.register(r'knowledge-sections', KnowledgeSectionViewSet, basename='knowledge-section')
router.register(r'knowledge-section-attachments', KnowledgeSectionAttachmentViewSet, basename='knowledge-section-attachment')
router.register(r'snippets', InfoSnippetViewSet, basename='snippet')
router.register(r'templates', DocumentTemplateViewSet, basename='template')
router.register(r'generated', GeneratedDocumentViewSet, basename='generateddocument')
router.register(r'knowledge-tests', KnowledgeTestViewSet, basename='knowledge-test')
router.register(r'knowledge-test-attempts', KnowledgeTestAttemptViewSet, basename='knowledge-test-attempt')

urlpatterns = [
    path('documents/', include(router.urls)),
]