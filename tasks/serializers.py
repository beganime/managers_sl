from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Task

User = get_user_model()


class TaskUserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'first_name', 'last_name', 'email')


class TaskSerializer(serializers.ModelSerializer):
    assigned_to_data = TaskUserMiniSerializer(source='assigned_to', read_only=True)
    created_by_data = TaskUserMiniSerializer(source='created_by', read_only=True)

    class Meta:
        model = Task
        fields = (
            'id',
            'title',
            'description',
            'assigned_to',
            'assigned_to_data',
            'created_by',
            'created_by_data',
            'client',
            'status',
            'priority',
            'deadline',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_by', 'created_at', 'updated_at')