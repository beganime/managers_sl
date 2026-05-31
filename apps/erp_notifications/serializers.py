from rest_framework import serializers

from .models import DeviceToken, Notification, NotificationBatch, NotificationLog, NotificationTemplate


class DeviceTokenSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)

    class Meta:
        model = DeviceToken
        fields = '__all__'
        read_only_fields = ('user', 'last_seen_at', 'created_at', 'updated_at')

    def validate_token(self, value):
        value = str(value or '').strip()
        if len(value) < 20:
            raise serializers.ValidationError('Device token is too short.')
        return value


class NotificationTemplateSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = NotificationTemplate
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')


class NotificationLogSerializer(serializers.ModelSerializer):
    notification_title = serializers.CharField(source='notification.title', read_only=True)
    device_platform = serializers.CharField(source='device_token.platform', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    channel_display = serializers.CharField(source='get_channel_display', read_only=True)

    class Meta:
        model = NotificationLog
        fields = '__all__'
        read_only_fields = ('created_at',)


class NotificationBatchSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    target_user_name = serializers.CharField(source='target_user.get_full_name', read_only=True)
    target_office_name = serializers.CharField(source='target_office.name', read_only=True)
    recipient_count = serializers.IntegerField(read_only=True)
    read_count = serializers.IntegerField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    read_percent = serializers.IntegerField(read_only=True)
    target_type_display = serializers.CharField(source='get_target_type_display', read_only=True)
    type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = NotificationBatch
        fields = '__all__'
        read_only_fields = ('sender', 'sent_at', 'created_at', 'updated_at')


class NotificationSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    recipient_name = serializers.CharField(source='recipient.get_full_name', read_only=True)
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)
    batch_title = serializers.CharField(source='batch.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    channel_display = serializers.CharField(source='get_channel_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    is_read = serializers.BooleanField(read_only=True)
    logs = NotificationLogSerializer(many=True, read_only=True)

    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = (
            'sender',
            'queued_at',
            'sent_at',
            'read_at',
            'failed_at',
            'error_message',
            'created_at',
            'updated_at',
        )
