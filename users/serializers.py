# users/serializers.py
from rest_framework import serializers
from .models import User, Office

class OfficeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Office
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    # Для удобства прокидываем название города офиса
    office_name = serializers.CharField(source='office.city', read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'email', 'first_name', 'last_name', 'middle_name', 
            'avatar', 'dob', 'office', 'office_name', 'job_description', 
            'work_status', 'social_contacts', 'is_effective', 'updated_at'
        )
        
        # Защищаем поля от изменения менеджером через профиль.
        # Эти данные может менять только HR или Админ через веб-версию.
        read_only_fields = ('email', 'office', 'job_description', 'is_effective', 'updated_at')