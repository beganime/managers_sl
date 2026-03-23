# reports/serializers.py
from rest_framework import serializers
from .models import DailyReport


class DailyReportSerializer(serializers.ModelSerializer):
    # ← Добавляем читаемое имя, чтобы мобилка показывала «Иван Иванов», а не просто ID
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model  = DailyReport
        fields = '__all__'
        read_only_fields = ('employee', 'created_at', 'updated_at')

    def get_employee_name(self, obj) -> str:
        u = obj.employee
        full = f'{u.first_name} {u.last_name}'.strip()
        return full or u.email