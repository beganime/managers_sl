from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DeviceTokenViewSet, NotificationBatchViewSet, NotificationLogViewSet, NotificationTemplateViewSet, NotificationViewSet

router = DefaultRouter()
router.register('device-tokens', DeviceTokenViewSet, basename='erp-notification-device-token')
router.register('batches', NotificationBatchViewSet, basename='erp-notification-batch')
router.register('templates', NotificationTemplateViewSet, basename='erp-notification-template')
router.register('logs', NotificationLogViewSet, basename='erp-notification-log')

notification_list = NotificationViewSet.as_view({'get': 'list', 'post': 'create'})
notification_detail = NotificationViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})
notification_mark_all_read = NotificationViewSet.as_view({'post': 'mark_all_read'})
notification_send_test = NotificationViewSet.as_view({'post': 'send_test'})
notification_mark_read = NotificationViewSet.as_view({'post': 'mark_read'})
notification_send = NotificationViewSet.as_view({'post': 'send'})

urlpatterns = [
    path('', notification_list, name='erp-notification-list'),
    path('mark-all-read/', notification_mark_all_read, name='erp-notification-mark-all-read'),
    path('send-test/', notification_send_test, name='erp-notification-send-test'),
    path('<int:pk>/', notification_detail, name='erp-notification-detail'),
    path('<int:pk>/mark-read/', notification_mark_read, name='erp-notification-mark-read'),
    path('<int:pk>/send/', notification_send, name='erp-notification-send'),
    path('', include(router.urls)),
]
