from rest_framework import serializers

from .models import SupportMessage


class SupportMessageSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = SupportMessage
        fields = (
            'id',
            'user',
            'user_name',
            'user_email',
            'category',
            'subject',
            'message',
            'status',
            'admin_note',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('user', 'user_name', 'user_email', 'status', 'admin_note', 'created_at', 'updated_at')

    def get_user_name(self, obj):
        if not obj.user:
            return None
        full = f'{obj.user.first_name} {obj.user.last_name}'.strip()
        return full or obj.user.email

    def validate_subject(self, value):
        value = str(value or '').strip()
        if len(value) < 3:
            raise serializers.ValidationError('Укажи тему обращения.')
        return value

    def validate_message(self, value):
        value = str(value or '').strip()
        if len(value) < 5:
            raise serializers.ValidationError('Сообщение слишком короткое.')
        return value