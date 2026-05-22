from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ProjectNoteViewSet,
    ProjectSectionViewSet,
    ProjectTaskViewSet,
    ProjectViewSet,
    TaskAttachmentViewSet,
    TaskChecklistItemViewSet,
    TaskChecklistViewSet,
    TaskCommentViewSet,
    TaskWatcherViewSet,
)

router = DefaultRouter()
router.register('sections', ProjectSectionViewSet, basename='project-v2-section')
router.register('tasks', ProjectTaskViewSet, basename='project-v2-task')
router.register('comments', TaskCommentViewSet, basename='project-v2-comment')
router.register('checklists', TaskChecklistViewSet, basename='project-v2-checklist')
router.register('checklist-items', TaskChecklistItemViewSet, basename='project-v2-checklist-item')
router.register('attachments', TaskAttachmentViewSet, basename='project-v2-attachment')
router.register('notes', ProjectNoteViewSet, basename='project-v2-note')
router.register('watchers', TaskWatcherViewSet, basename='project-v2-watcher')

project_list = ProjectViewSet.as_view({'get': 'list', 'post': 'create'})
project_detail = ProjectViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})

urlpatterns = [
    path('', project_list, name='project-v2-list'),
    path('<int:pk>/', project_detail, name='project-v2-detail'),
    path('', include(router.urls)),
]
