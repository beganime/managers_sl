# timetracking/serializers.py
from rest_framework import serializers
from .models import WorkShift


class WorkShiftSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkShift
        fields = '__all__'
        read_only_fields = ('employee', 'hours_worked', 'updated_at')

    def get_employee_name(self, obj):
        if not obj.employee:
            return "Неизвестный"
        full = f"{obj.employee.first_name} {obj.employee.last_name}".strip()
        return full or obj.employee.email