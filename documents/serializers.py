# documents/serializers.py
from rest_framework import serializers
from .models import InfoSnippet, ContractTemplate, Contract

class InfoSnippetSerializer(serializers.ModelSerializer):
    class Meta:
        model = InfoSnippet
        fields = '__all__'

class ContractTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractTemplate
        fields = '__all__'

class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = '__all__'
        # Файл и статус генерирует админ, менеджер с мобилки менять их не должен
        read_only_fields = ('manager', 'status', 'generated_file', 'created_at', 'updated_at')