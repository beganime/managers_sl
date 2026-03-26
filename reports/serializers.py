# reports/serializers.py
from rest_framework import serializers
from .models import DailyReport


class DailyReportSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    net_result = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = DailyReport
        fields = '__all__'
        read_only_fields = ('employee', 'created_at', 'updated_at')

    def get_employee_name(self, obj) -> str:
        if not obj.employee:
            return "Неизвестный"
        full = f'{obj.employee.first_name} {obj.employee.last_name}'.strip()
        return full or obj.employee.email

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        instance = getattr(self, 'instance', None)

        report_date = attrs.get('date')
        if instance and report_date is None:
            report_date = instance.date

        if not report_date:
            return attrs

        qs = DailyReport.objects.filter(employee=user, date=report_date)
        if instance:
            qs = qs.exclude(pk=instance.pk)

        if user and qs.exists():
            raise serializers.ValidationError({
                'date': 'Отчёт за эту дату уже существует.'
            })

        return attrs