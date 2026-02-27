# timetracking/serializers.py
from rest_framework import serializers
from .models import WorkShift

class WorkShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkShift
        fields = '__all__'
        read_only_fields = ('employee', 'hours_worked', 'updated_at')