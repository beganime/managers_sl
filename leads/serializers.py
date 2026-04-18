# leads/serializers.py
import re
from rest_framework import serializers

from .models import Lead


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = '__all__'

    def validate_full_name(self, value):
        # Защита от спама: блокируем имена, где 5 и более одинаковых символов подряд (xxxxx)
        if value and re.search(r'(.)\1{4,}', value.lower()):
            raise serializers.ValidationError("Имя содержит недопустимое количество повторяющихся символов.")
        return value

    def validate_student_name(self, value):
        # Аналогичная защита для ФИО студента
        if value and re.search(r'(.)\1{4,}', value.lower()):
            raise serializers.ValidationError("ФИО содержит недопустимое количество повторяющихся символов.")
        return value

    def validate_parent_name(self, value):
        # Аналогичная защита для ФИО родителя
        if value and re.search(r'(.)\1{4,}', value.lower()):
            raise serializers.ValidationError("ФИО содержит недопустимое количество повторяющихся символов.")
        return value

    def validate_phone(self, value):
        # Защита от кривых номеров телефона
        cleaned = re.sub(r'\D', '', str(value))
        if len(cleaned) < 6:
            raise serializers.ValidationError("Некорректный номер телефона.")
        return value

    def to_internal_value(self, data):
        """
        Перехватываем JSON перед сохранением и переводим русские ключи
        из формы в английские поля модели Django.
        """
        mapping = {
            'ФИО студента': 'student_name',
            'ФИО родителя': 'parent_name',
            'Наличие паспорта': 'has_passport',
            'Срок действия паспорта': 'passport_expiry',
            'Месяц поездки': 'travel_month',
            'Город вылета': 'departure_city',
            'Город прибытия': 'arrival_city',
            'Дата поездки': 'travel_date',
            'Багаж': 'luggage',
            'Текущее образование': 'current_education',
            'Текущий университет': 'current_university',
            'Текущая страна': 'current_country',
        }

        mutable_data = data.copy() if hasattr(data, 'copy') else data

        for ru_key, eng_field in mapping.items():
            if ru_key in mutable_data:
                mutable_data[eng_field] = mutable_data.pop(ru_key)

        date_fields = ['passport_expiry', 'travel_date']
        for df in date_fields:
            if df in mutable_data and mutable_data.get(df) == '':
                mutable_data[df] = None

        return super().to_internal_value(mutable_data)


class MobileLeadSerializer(serializers.ModelSerializer):
    manager_name = serializers.SerializerMethodField()
    manager_email = serializers.EmailField(source='manager.email', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'manager_name', 'manager_email')

    def get_manager_name(self, obj):
        if not obj.manager:
            return None
        full = f'{obj.manager.first_name} {obj.manager.last_name}'.strip()
        return full or obj.manager.email