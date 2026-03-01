# users/serializers.py
from rest_framework import serializers
from .models import User, ManagerSalary, Office

class ManagerSalarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagerSalary
        fields = '__all__'

class OfficeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Office
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    # Явно вкладываем профиль с планом продаж и мотивацией
    managersalary = ManagerSalarySerializer(read_only=True)
    office = OfficeSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'middle_name', 
            'avatar', 'work_status', 'is_effective', 'managersalary', 'office'
        ]