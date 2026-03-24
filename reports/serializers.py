# reports/serializers.py
from rest_framework import serializers
from .models import DailyReport

class DailyReportSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model  = DailyReport
        fields = '__all__'
        read_only_fields = ('employee', 'created_at', 'updated_at')

    def get_employee_name(self, obj) -> str:
        if not obj.employee:
            return "Неизвестный"
        full = f'{obj.employee.first_name} {obj.employee.last_name}'.strip()
        return full or obj.employee.email