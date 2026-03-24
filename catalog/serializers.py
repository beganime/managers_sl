# catalog/serializers.py
from rest_framework import serializers
from .models import Currency, University, Program

class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = '__all__'

class ProgramSerializer(serializers.ModelSerializer):
    class Meta:
        model = Program
        fields = '__all__'

class UniversitySerializer(serializers.ModelSerializer):
    programs = ProgramSerializer(many=True, read_only=True)
    # ВАЖНО: Теперь мы отдаем валюту как объект, а не просто ID
    local_currency = CurrencySerializer(read_only=True)
    
    class Meta:
        model = University
        fields = '__all__'