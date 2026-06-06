from rest_framework import serializers

from .models import AttendanceReminder, AutoCloseLog, DailyReport, WorkDay, WorkSession


class WorkSessionSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = WorkSession
        fields = '__all__'
        read_only_fields = ('duration_seconds', 'is_active', 'created_at', 'updated_at')


class DailyReportSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    workday_status = serializers.CharField(source='workday.status', read_only=True)

    class Meta:
        model = DailyReport
        fields = '__all__'
        read_only_fields = ('company', 'office', 'employee', 'date', 'submitted_at', 'created_at', 'updated_at')

    def validate_content(self, value):
        if not str(value or '').strip():
            raise serializers.ValidationError('Daily report content is required.')
        return value


class WorkDaySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_work_hours = serializers.FloatField(read_only=True)
    has_report = serializers.BooleanField(read_only=True)
    sessions = WorkSessionSerializer(many=True, read_only=True)
    daily_report = DailyReportSerializer(read_only=True)

    class Meta:
        model = WorkDay
        fields = '__all__'
        read_only_fields = (
            'status',
            'started_at',
            'closed_at',
            'auto_closed_at',
            'total_work_seconds',
            'created_at',
            'updated_at',
        )


class WorkDayHistorySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_work_hours = serializers.FloatField(read_only=True)
    has_report = serializers.BooleanField(read_only=True)
    report_text = serializers.SerializerMethodField()

    class Meta:
        model = WorkDay
        fields = (
            'id',
            'date',
            'started_at',
            'closed_at',
            'status',
            'status_display',
            'total_work_seconds',
            'total_work_hours',
            'has_report',
            'report_text',
            'employee',
            'employee_name',
            'office',
            'office_name',
            'company',
            'company_name',
        )
        read_only_fields = fields

    def get_report_text(self, obj):
        report = getattr(obj, 'daily_report', None)
        if report and report.content:
            return report.content
        return obj.comment or ''


class AttendanceReminderSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    reminder_type_display = serializers.CharField(source='get_reminder_type_display', read_only=True)

    class Meta:
        model = AttendanceReminder
        fields = '__all__'
        read_only_fields = ('last_sent_at', 'created_at', 'updated_at')


class AutoCloseLogSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)

    class Meta:
        model = AutoCloseLog
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
