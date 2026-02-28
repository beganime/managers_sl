# leads/serializers.py
from rest_framework import serializers
from .models import Lead

class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        # Разрешаем принимать все поля
        fields = '__all__'
        
    def to_internal_value(self, data):
        """
        Магия: Перехватываем JSON перед сохранением и переводим русские ключи 
        из вашей формы в английские поля модели Django.
        """
        mapping = {
            "ФИО студента": "student_name",
            "ФИО родителя": "parent_name",
            "Наличие паспорта": "has_passport",
            "Срок действия паспорта": "passport_expiry",
            "Месяц поездки": "travel_month",
            "Город вылета": "departure_city",
            "Город прибытия": "arrival_city",
            "Дата поездки": "travel_date",
            "Багаж": "luggage",
            "Текущее образование": "current_education",
            "Текущий университет": "current_university",
            "Текущая страна": "current_country",
        }
        
        # Создаем изменяемую копию данных
        mutable_data = data.copy() if hasattr(data, 'copy') else data
        
        # Переименовываем ключи
        for ru_key, eng_field in mapping.items():
            if ru_key in mutable_data:
                mutable_data[eng_field] = mutable_data.pop(ru_key)
                
        # Защита: Если вместо даты прислали пустую строку "", ставим null, чтобы БД не выдала ошибку
        date_fields = ["passport_expiry", "travel_date"]
        for df in date_fields:
            if df in mutable_data and mutable_data.get(df) == "":
                mutable_data[df] = None
                
        return super().to_internal_value(mutable_data)

# Новый сериализатор для мобильного приложения (чтение и обновление)
class LeadMobileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ['id', 'full_name', 'phone', 'direction', 'status', 'created_at']