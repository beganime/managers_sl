from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.core.permissions import filter_by_office_scope, get_employee_profile, is_erp_admin

from .models import DeviceToken, Notification, NotificationLog, NotificationTemplate
from .serializers import (
    DeviceTokenSerializer,
    NotificationLogSerializer,
    NotificationSerializer,
    NotificationTemplateSerializer,
)
from .services import create_notification, send_notification


TRUE_VALUES = {'1', 'true', 'True', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'False', 'no', 'off'}


def parse_bool(value):
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None


def default_company_office(user):
    employee = get_employee_profile(user)
    if not employee:
        return {}
    data = {'company': employee.company}
    if employee.office_id:
        data['office'] = employee.office
    return data


def apply_common_filters(qs, request, *, search_fields=(), date_field='created_at'):
    company = request.query_params.get('company')
    if company and hasattr(qs.model, 'company'):
        qs = qs.filter(company_id=company)

    office = request.query_params.get('office')
    if office and hasattr(qs.model, 'office'):
        qs = qs.filter(office_id=office)

    status_value = request.query_params.get('status')
    if status_value and hasattr(qs.model, 'status'):
        qs = qs.filter(status=status_value)

    notification_type = request.query_params.get('type') or request.query_params.get('notification_type')
    if notification_type and hasattr(qs.model, 'notification_type'):
        qs = qs.filter(notification_type=notification_type)

    channel = request.query_params.get('channel')
    if channel and hasattr(qs.model, 'channel'):
        qs = qs.filter(channel=channel)

    recipient = request.query_params.get('recipient')
    if recipient and hasattr(qs.model, 'recipient'):
        qs = qs.filter(recipient_id=recipient)

    user = request.query_params.get('user')
    if user and hasattr(qs.model, 'user'):
        qs = qs.filter(user_id=user)

    is_active = parse_bool(request.query_params.get('is_active'))
    if is_active is not None and hasattr(qs.model, 'is_active'):
        qs = qs.filter(is_active=is_active)

    date_from = request.query_params.get('date_from')
    if date_from and date_field and hasattr(qs.model, date_field):
        qs = qs.filter(**{f'{date_field}__gte': date_from})

    date_to = request.query_params.get('date_to')
    if date_to and date_field and hasattr(qs.model, date_field):
        qs = qs.filter(**{f'{date_field}__lte': date_to})

    search = request.query_params.get('search')
    if search and search_fields:
        query = Q()
        for field in search_fields:
            query |= Q(**{f'{field}__icontains': search})
        qs = qs.filter(query)

    return qs


class DeviceTokenViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceTokenSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DeviceToken.objects.select_related('company', 'office', 'user')
        if not is_erp_admin(self.request.user):
            qs = qs.filter(user=self.request.user)
        return apply_common_filters(qs, self.request, search_fields=('user__email', 'device_name', 'token')).order_by('-last_seen_at')

    def create(self, request, *args, **kwargs):
        return self.register(request)

    @action(detail=False, methods=['post'], url_path='register')
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']
        DeviceToken.objects.filter(token=token).exclude(user=request.user).delete()

        defaults = {
            'user': request.user,
            'platform': serializer.validated_data.get('platform') or DeviceToken.PLATFORM_UNKNOWN,
            'device_name': serializer.validated_data.get('device_name', ''),
            'app_version': serializer.validated_data.get('app_version', ''),
            'locale': serializer.validated_data.get('locale', ''),
            'timezone': serializer.validated_data.get('timezone', ''),
            'is_active': True,
            'last_seen_at': timezone.now(),
        }
        scope = default_company_office(request.user)
        defaults['company'] = serializer.validated_data.get('company') or scope.get('company')
        defaults['office'] = serializer.validated_data.get('office') or scope.get('office')

        device, _ = DeviceToken.objects.update_or_create(token=token, defaults=defaults)
        return Response(self.get_serializer(device).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='unregister')
    def unregister(self, request):
        token = str(request.data.get('token') or '').strip()
        if not token:
            raise ValidationError({'token': 'Token is required.'})
        DeviceToken.objects.filter(user=request.user, token=token).update(is_active=False)
        return Response({'detail': 'Device token disabled.'}, status=status.HTTP_200_OK)


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = NotificationTemplate.objects.select_related('company', 'created_by')
        if not is_erp_admin(self.request.user):
            employee = get_employee_profile(self.request.user)
            if not employee:
                qs = qs.filter(company__isnull=True)
            else:
                qs = qs.filter(Q(company=employee.company) | Q(company__isnull=True))
        return apply_common_filters(qs, self.request, search_fields=('name', 'code', 'title_template', 'body_template')).order_by('company__name', 'code')

    def perform_create(self, serializer):
        if not is_erp_admin(self.request.user):
            raise PermissionDenied('Only administrators can create notification templates.')
        serializer.save(created_by=self.request.user)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.select_related('company', 'office', 'recipient', 'sender', 'template', 'content_type').prefetch_related('logs')
        if not is_erp_admin(self.request.user):
            qs = qs.filter(recipient=self.request.user)
        else:
            qs = filter_by_office_scope(qs, self.request.user)

        unread = parse_bool(self.request.query_params.get('unread'))
        if unread is True:
            qs = qs.filter(read_at__isnull=True).exclude(status=Notification.STATUS_READ)
        elif unread is False:
            qs = qs.filter(Q(read_at__isnull=False) | Q(status=Notification.STATUS_READ))

        return apply_common_filters(
            qs,
            self.request,
            search_fields=('title', 'body', 'recipient__email', 'recipient__first_name', 'recipient__last_name'),
        ).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_read()
        return Response(self.get_serializer(notification).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        qs = self.get_queryset().exclude(status=Notification.STATUS_READ)
        now = timezone.now()
        count = qs.update(status=Notification.STATUS_READ, read_at=now, updated_at=now)
        return Response({'updated': count}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='send')
    def send(self, request, pk=None):
        if not is_erp_admin(request.user):
            raise PermissionDenied('Only administrators can force-send notifications.')
        notification = self.get_object()
        send_notification(notification)
        return Response(self.get_serializer(notification).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='send-test')
    def send_test(self, request):
        title = request.data.get('title') or 'Test notification'
        body = request.data.get('body') or 'ERP notification channel is ready.'
        notification = create_notification(
            request.user,
            title=title,
            body=body,
            notification_type=NotificationTemplate.TYPE_SYSTEM,
            channel=request.data.get('channel') or NotificationTemplate.CHANNEL_IN_APP,
            priority=Notification.PRIORITY_NORMAL,
            data={'source': 'send_test'},
            queue=True,
        )
        send_notification(notification)
        return Response(self.get_serializer(notification).data, status=status.HTTP_201_CREATED)


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = NotificationLog.objects.select_related('notification', 'notification__recipient', 'device_token')
        if not is_erp_admin(self.request.user):
            qs = qs.filter(notification__recipient=self.request.user)

        notification = self.request.query_params.get('notification')
        if notification:
            qs = qs.filter(notification_id=notification)

        channel = self.request.query_params.get('channel')
        if channel:
            qs = qs.filter(channel=channel)

        status_value = self.request.query_params.get('status')
        if status_value:
            qs = qs.filter(status=status_value)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(notification__title__icontains=search) | Q(recipient__icontains=search) | Q(error_message__icontains=search))

        return qs.order_by('-created_at')
