from rest_framework import serializers
from .models import Notification, Leaderboard, TutorialVideo


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = (
            'recipient',
            'title',
            'body',
            'created_at',
            'updated_at',
            'fcm_message_id',
        )


class TutorialVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TutorialVideo
        fields = (
            'id',
            'title',
            'description',
            'video_file',
            'youtube_url',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')

    def validate(self, attrs):
        video_file = attrs.get('video_file')
        youtube_url = attrs.get('youtube_url')

        instance = getattr(self, 'instance', None)
        if instance:
            if video_file is None:
                video_file = instance.video_file
            if youtube_url is None:
                youtube_url = instance.youtube_url

        if not video_file and not youtube_url:
            raise serializers.ValidationError(
                'Нужно указать либо файл видео, либо ссылку YouTube.'
            )

        return attrs


class LeaderboardSerializer(serializers.ModelSerializer):
    revenue = serializers.SerializerMethodField()
    office_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    office = serializers.SerializerMethodField()

    class Meta:
        model = Leaderboard
        fields = (
            'id',
            'first_name',
            'last_name',
            'full_name',
            'avatar_url',
            'office_name',
            'office',
            'revenue',
        )

    def get_full_name(self, obj):
        full = f"{obj.first_name} {obj.last_name}".strip()
        return full or obj.email or 'Сотрудник'

    def get_revenue(self, obj):
        try:
            if hasattr(obj, 'managersalary') and obj.managersalary:
                val = obj.managersalary.current_month_revenue
                return float(val if val is not None else 0.00)
        except Exception:
            pass
        return 0.00

    def get_office_name(self, obj):
        try:
            if hasattr(obj, 'office') and obj.office:
                return obj.office.city or "Без офиса"
        except Exception:
            pass
        return "Без офиса"

    def get_office(self, obj):
        try:
            if hasattr(obj, 'office') and obj.office:
                return {
                    'id': obj.office.id,
                    'city': obj.office.city or 'Без офиса',
                    'address': obj.office.address or '',
                    'phone': obj.office.phone or '',
                }
        except Exception:
            pass
        return None

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