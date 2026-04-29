from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ProjectAttachmentViewSet,
    ProjectSectionPostViewSet,
    ProjectSectionViewSet,
    ProjectTaskViewSet,
    ProjectViewSet,
    TaskViewSet,
)

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'project-sections', ProjectSectionViewSet, basename='project-section')
router.register(r'project-section-posts', ProjectSectionPostViewSet, basename='project-section-post')
router.register(r'project-tasks', ProjectTaskViewSet, basename='project-task')
router.register(r'project-attachments', ProjectAttachmentViewSet, basename='project-attachment')
router.register(r'', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
]