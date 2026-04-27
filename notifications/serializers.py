from rest_framework import serializers

from .models import FCMDevice


class FCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMDevice
        fields = (
            'id',
            'token',
            'platform',
            'device_name',
            'is_active',
            'last_seen_at',
            'created_at',
        )
        read_only_fields = ('id', 'is_active', 'last_seen_at', 'created_at')

    def validate_token(self, value):
        value = str(value or '').strip()
        if len(value) < 20:
            raise serializers.ValidationError('Некорректный Firebase token.')
        return value