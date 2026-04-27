from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import FCMDevice
from .serializers import FCMDeviceSerializer


class FCMDeviceViewSet(viewsets.ModelViewSet):
    serializer_class = FCMDeviceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FCMDevice.objects.filter(user=self.request.user).order_by('-last_seen_at')

    def perform_create(self, serializer):
        token = serializer.validated_data.get('token')
        FCMDevice.objects.filter(token=token).exclude(user=self.request.user).delete()
        serializer.save(user=self.request.user, is_active=True)

    def perform_update(self, serializer):
        serializer.save(user=self.request.user, is_active=True)

    @action(detail=False, methods=['post'], url_path='register')
    def register(self, request):
        token = str(request.data.get('token') or '').strip()
        if not token:
            return Response({'detail': 'token обязателен'}, status=status.HTTP_400_BAD_REQUEST)

        platform = str(request.data.get('platform') or 'unknown').strip() or 'unknown'
        device_name = str(request.data.get('device_name') or '').strip()

        FCMDevice.objects.filter(token=token).exclude(user=request.user).delete()
        device, _ = FCMDevice.objects.update_or_create(
            token=token,
            defaults={
                'user': request.user,
                'platform': platform,
                'device_name': device_name,
                'is_active': True,
            },
        )

        return Response(FCMDeviceSerializer(device, context={'request': request}).data)

    @action(detail=False, methods=['post'], url_path='unregister')
    def unregister(self, request):
        token = str(request.data.get('token') or '').strip()
        if token:
            FCMDevice.objects.filter(user=request.user, token=token).update(is_active=False)
        return Response({'detail': 'Устройство отключено'})