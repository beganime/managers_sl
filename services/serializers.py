# services/serializers.py
from rest_framework import serializers
from .models import Service

class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        # Указываем поля явно, ИСКЛЮЧАЯ real_cost
        fields = ('id', 'title', 'description', 'price_client', 'is_active', 'updated_at')