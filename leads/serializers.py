# leads/serializers.py
import re

from rest_framework import serializers

from .models import Lead


def normalize_phone(value) -> str:
    return re.sub(r'\D', '', str(value or ''))


def starts_with_test(value) -> bool:
    value = str(value or '').strip().casefold()
    return value.startswith('test') or value.startswith('тест')


def email_starts_with_test(value) -> bool:
    value = str(value or '').strip().casefold()

    if not value:
        return False

    local_part = value.split('@', 1)[0]
    return local_part.startswith('test') or local_part.startswith('тест')


def has_too_many_repeated_chars(value) -> bool:
    return bool(value and re.search(r'(.)\1{4,}', str(value).casefold()))


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = (
            'id',
            'manager',
            'status',
            'created_at',
            'updated_at',
            'submitter_ip',
            'submitter_user_agent',
            'submitter_referer',
            'submitter_origin',
            'submitter_host',
        )

    def validate_full_name(self, value):
        if starts_with_test(value):
            raise serializers.ValidationError("Тестовые имена не принимаются.")

        if has_too_many_repeated_chars(value):
            raise serializers.ValidationError("Имя содержит недопустимое количество повторяющихся символов.")

        return value

    def validate_student_name(self, value):
        if starts_with_test(value):
            raise serializers.ValidationError("Тестовые ФИО не принимаются.")

        if has_too_many_repeated_chars(value):
            raise serializers.ValidationError("ФИО содержит недопустимое количество повторяющихся символов.")

        return value

    def validate_parent_name(self, value):
        if starts_with_test(value):
            raise serializers.ValidationError("Тестовые ФИО не принимаются.")

        if has_too_many_repeated_chars(value):
            raise serializers.ValidationError("ФИО содержит недопустимое количество повторяющихся символов.")

        return value

    def validate_email(self, value):
        if email_starts_with_test(value):
            raise serializers.ValidationError("Тестовые email не принимаются.")

        return value

    def validate_phone(self, value):
        cleaned = normalize_phone(value)

        if len(cleaned) < 6:
            raise serializers.ValidationError("Некорректный номер телефона.")

        return value

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)

        email = attrs.get('email')
        phone = attrs.get('phone')
        phone_digits = normalize_phone(phone)

        duplicates = Lead.objects.all()

        if instance and instance.pk:
            duplicates = duplicates.exclude(pk=instance.pk)

        if email:
            if duplicates.filter(email__iexact=str(email).strip()).exists():
                raise serializers.ValidationError(
                    {'email': 'Такая заявка уже есть. Дубликат не принят.'}
                )

        if phone_digits:
            possible_phone_duplicates = duplicates.only('id', 'phone')

            for lead in possible_phone_duplicates:
                if normalize_phone(lead.phone) == phone_digits:
                    raise serializers.ValidationError(
                        {'phone': 'Такая заявка уже есть. Дубликат не принят.'}
                    )

        return attrs

    def to_internal_value(self, data):
        """
        Не меняем frontend/mobile JSON.
        Здесь сервер сам переводит русские ключи формы в поля модели.
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

        mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)

        for ru_key, eng_field in mapping.items():
            if ru_key in mutable_data:
                mutable_data[eng_field] = mutable_data.pop(ru_key)

        date_fields = ['passport_expiry', 'travel_date']

        for field_name in date_fields:
            if field_name in mutable_data and mutable_data.get(field_name) == '':
                mutable_data[field_name] = None

        return super().to_internal_value(mutable_data)


class MobileLeadSerializer(serializers.ModelSerializer):
    manager_name = serializers.SerializerMethodField()
    manager_email = serializers.EmailField(source='manager.email', read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
        read_only_fields = (
            'created_at',
            'updated_at',
            'manager_name',
            'manager_email',
            'submitter_ip',
            'submitter_user_agent',
            'submitter_referer',
            'submitter_origin',
            'submitter_host',
        )

    def get_manager_name(self, obj):
        if not obj.manager:
            return None

        full = f'{obj.manager.first_name} {obj.manager.last_name}'.strip()
        return full or obj.manager.email