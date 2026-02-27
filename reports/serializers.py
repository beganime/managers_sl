# reports/serializers.py
from rest_framework import serializers
from .models import DailyReport

class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        fields = '__all__'
        read_only_fields = ('employee', 'created_at', 'updated_at')