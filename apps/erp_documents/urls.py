from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DocumentApprovalViewSet,
    DocumentDownloadLogViewSet,
    DocumentTemplateFieldViewSet,
    DocumentTemplateViewSet,
    GeneratedDocumentViewSet,
    StampRuleViewSet,
)

router = DefaultRouter()
router.register('templates', DocumentTemplateViewSet, basename='erp-document-template')
router.register('template-fields', DocumentTemplateFieldViewSet, basename='erp-document-template-field')
router.register('generated', GeneratedDocumentViewSet, basename='erp-generated-document')
router.register('approvals', DocumentApprovalViewSet, basename='erp-document-approval')
router.register('stamp-rules', StampRuleViewSet, basename='erp-document-stamp-rule')
router.register('download-logs', DocumentDownloadLogViewSet, basename='erp-document-download-log')

urlpatterns = [
    path('', include(router.urls)),
]
