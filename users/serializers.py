# users/serializers.py
from rest_framework import serializers
from .models import User, ManagerSalary, Office

class ManagerSalarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagerSalary
        fields = '__all__'

class OfficeSerializer(serializers.ModelSerializer):
    # Явно указываем новое поле дохода офиса
    monthly_revenue = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = Office
        fields = ['id', 'city', 'address', 'phone', 'monthly_revenue', 'updated_at']

class UserSerializer(serializers.ModelSerializer):
    managersalary = ManagerSalarySerializer(read_only=True)
    office = OfficeSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'middle_name', 
            'avatar', 'dob', 'social_contacts', 'job_description', 
            'work_status', 'is_effective', 'managersalary', 'office',
            'is_superuser', 'is_staff'  # <-- ИСПРАВЛЕНИЕ: Теперь мобилка знает, что ты Админ!
        ]