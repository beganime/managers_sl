# gamification/serializers.py
from rest_framework import serializers
from .models import Notification, Leaderboard

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('recipient', 'title', 'body', 'created_at', 'updated_at', 'fcm_message_id')

class LeaderboardSerializer(serializers.ModelSerializer):
    # Используем безопасные методы вместо прямого source
    revenue = serializers.SerializerMethodField()
    office_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Leaderboard
        fields = ('id', 'first_name', 'last_name', 'avatar_url', 'office_name', 'revenue')

    def get_revenue(self, obj):
        try:
            if hasattr(obj, 'managersalary') and obj.managersalary:
                val = obj.managersalary.current_month_revenue
                return val if val is not None else 0.00
        except Exception:
            pass
        return 0.00

    def get_office_name(self, obj):
        try:
            if hasattr(obj, 'office') and obj.office:
                return obj.office.city or "—"
        except Exception:
            pass
        return "—"

    def get_avatar_url(self, obj):
        try:
            if hasattr(obj, 'avatar') and obj.avatar and hasattr(obj.avatar, 'url'):
                request = self.context.get('request')
                if request is not None:
                    return request.build_absolute_uri(obj.avatar.url)
                return obj.avatar.url
        except Exception:
            pass
        return None