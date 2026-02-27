# clients/serializers.py
from rest_framework import serializers
from .models import Client, ClientRelative

class ClientRelativeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientRelative
        fields = '__all__'
        read_only_fields = ('client',)

class ClientSerializer(serializers.ModelSerializer):
    # Вкладываем данные родственника прямо в ответ клиента
    relative = ClientRelativeSerializer(read_only=True)
    
    class Meta:
        model = Client
        fields = '__all__'
        # Менеджера будем проставлять автоматически на бэкенде
        read_only_fields = ('manager', 'created_at', 'updated_at')