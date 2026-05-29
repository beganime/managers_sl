from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ApplicationViewSet,
    ClientActivityViewSet,
    ClientFileViewSet,
    ClientNoteViewSet,
    ClientViewSet,
    IncomingLeadViewSet,
    LeadSourceViewSet,
    LeadViewSet,
)

router = DefaultRouter()
router.register('lead-sources', LeadSourceViewSet, basename='crm-lead-source')
router.register('leads', LeadViewSet, basename='crm-lead')
router.register('incoming-leads', IncomingLeadViewSet, basename='crm-incoming-lead')
router.register('clients', ClientViewSet, basename='crm-client')
router.register('applications', ApplicationViewSet, basename='crm-application')
router.register('activities', ClientActivityViewSet, basename='crm-activity')
router.register('notes', ClientNoteViewSet, basename='crm-note')
router.register('files', ClientFileViewSet, basename='crm-file')

urlpatterns = [
    path('', include(router.urls)),
]
