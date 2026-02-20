from rest_framework import serializers
from .models import Lead

class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        # Перечисляем поля, которые разрешено передавать в POST-запросе
        fields = ['full_name', 'email', 'phone', 'country', 'education', 'age', 'relation', 'direction']