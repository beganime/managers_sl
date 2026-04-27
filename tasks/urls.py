from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProjectAttachmentViewSet, ProjectTaskViewSet, ProjectViewSet, TaskViewSet

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'project-tasks', ProjectTaskViewSet, basename='project-task')
router.register(r'project-attachments', ProjectAttachmentViewSet, basename='project-attachment')
router.register(r'', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
]