from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ArticleReadLogViewSet,
    KnowledgeArticleViewSet,
    KnowledgeAttachmentViewSet,
    KnowledgeCategoryViewSet,
    KnowledgeQuestionViewSet,
    KnowledgeTestAttemptViewSet,
    KnowledgeTestViewSet,
)

router = DefaultRouter()
router.register('categories', KnowledgeCategoryViewSet, basename='knowledge-category')
router.register('articles', KnowledgeArticleViewSet, basename='knowledge-article')
router.register('attachments', KnowledgeAttachmentViewSet, basename='knowledge-attachment')
router.register('tests', KnowledgeTestViewSet, basename='knowledge-test')
router.register('questions', KnowledgeQuestionViewSet, basename='knowledge-question')
router.register('attempts', KnowledgeTestAttemptViewSet, basename='knowledge-attempt')
router.register('read-logs', ArticleReadLogViewSet, basename='knowledge-read-log')

urlpatterns = [
    path('', include(router.urls)),
]
