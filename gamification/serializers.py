# gamification/serializers.py
from rest_framework import serializers
from .models import Notification, Leaderboard

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        # Разрешаем менять только статус "прочитано"
        read_only_fields = ('recipient', 'title', 'body', 'created_at', 'updated_at', 'fcm_message_id')

class LeaderboardSerializer(serializers.ModelSerializer):
    # Вытаскиваем выручку из связанной таблицы ManagerSalary
    revenue = serializers.DecimalField(
        source='managersalary.current_month_revenue',
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    # Вытаскиваем название города офиса
    office_name = serializers.CharField(
        source='office.city',
        read_only=True,
        default="—"
    )
    avatar_url = serializers.ImageField(source='avatar', read_only=True)

    class Meta:
        model = Leaderboard
        fields = ('id', 'first_name', 'last_name', 'avatar_url', 'office_name', 'revenue')