from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ApplicationViewSet,
    ApplicationExamViewSet,
    ClientActivityViewSet,
    ClientFileViewSet,
    ClientNoteViewSet,
    ClientViewSet,
    ExternalAccountViewSet,
    IncomingLeadViewSet,
    LeadSourceViewSet,
    LeadViewSet,
    Student360View,
)

router = DefaultRouter()
router.register('lead-sources', LeadSourceViewSet, basename='crm-lead-source')
router.register('leads', LeadViewSet, basename='crm-lead')
router.register('incoming-leads', IncomingLeadViewSet, basename='crm-incoming-lead')
router.register('clients', ClientViewSet, basename='crm-client')
router.register('applications', ApplicationViewSet, basename='crm-application')
router.register('application-exams', ApplicationExamViewSet, basename='crm-application-exam')
router.register('external-accounts', ExternalAccountViewSet, basename='crm-external-account')
router.register('activities', ClientActivityViewSet, basename='crm-activity')
router.register('notes', ClientNoteViewSet, basename='crm-note')
router.register('files', ClientFileViewSet, basename='crm-file')

urlpatterns = [
    path('students/<uuid:public_id>/360/', Student360View.as_view(), name='student-360'),
    path('', include(router.urls)),
]
