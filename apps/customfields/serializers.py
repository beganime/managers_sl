from decimal import Decimal, InvalidOperation

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from .models import CustomField, CustomFieldOption, CustomFieldValue


TRUE_VALUES = {True, 1, '1', 'true', 'True', 'yes', 'on'}
FALSE_VALUES = {False, 0, '0', 'false', 'False', 'no', 'off'}


def empty_value(value):
    return value is None or value == '' or value == [] or value == {}


def extract_value(value):
    if isinstance(value, dict) and set(value.keys()) == {'value'}:
        return value.get('value')
    return value


def normalize_field_value(field, value):
    value = extract_value(value)

    if field.field_type in (CustomField.TYPE_TEXT, CustomField.TYPE_TEXTAREA, CustomField.TYPE_DATE, CustomField.TYPE_DATETIME, CustomField.TYPE_FILE):
        return value

    if field.field_type == CustomField.TYPE_JSON:
        return value

    if field.field_type == CustomField.TYPE_USER:
        if empty_value(value):
            return value
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError('User field value must be a user id.') from exc

    if field.field_type == CustomField.TYPE_BOOLEAN:
        if value in TRUE_VALUES:
            return True
        if value in FALSE_VALUES:
            return False
        raise serializers.ValidationError('Boolean field value must be true or false.')

    if field.field_type == CustomField.TYPE_NUMBER:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError('Number field value must be an integer.') from exc

    if field.field_type == CustomField.TYPE_DECIMAL:
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise serializers.ValidationError('Decimal field value must be numeric.') from exc

    if field.field_type == CustomField.TYPE_SELECT:
        allowed = set(field.options.filter(is_active=True).values_list('value', flat=True))
        normalized = str(value)
        if allowed and normalized not in allowed:
            raise serializers.ValidationError('Select value is not one of active field options.')
        return normalized

    if field.field_type == CustomField.TYPE_MULTI_SELECT:
        if not isinstance(value, list):
            raise serializers.ValidationError('Multi select value must be a list.')
        normalized = [str(item) for item in value]
        allowed = set(field.options.filter(is_active=True).values_list('value', flat=True))
        if allowed and not set(normalized).issubset(allowed):
            raise serializers.ValidationError('Multi select contains inactive or unknown options.')
        return normalized

    return value


class CustomFieldOptionSerializer(serializers.ModelSerializer):
    field_name = serializers.CharField(source='field.name', read_only=True)

    class Meta:
        model = CustomFieldOption
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class CustomFieldSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    content_type_label = serializers.SerializerMethodField()
    options = CustomFieldOptionSerializer(many=True, read_only=True)

    class Meta:
        model = CustomField
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

    def get_content_type_label(self, obj):
        if not obj.content_type_id:
            return ''
        return f'{obj.content_type.app_label}.{obj.content_type.model}'


class CustomFieldValueSerializer(serializers.ModelSerializer):
    field_name = serializers.CharField(source='field.name', read_only=True)
    field_code = serializers.CharField(source='field.code', read_only=True)
    field_type = serializers.CharField(source='field.field_type', read_only=True)
    content_type_label = serializers.SerializerMethodField()
    content_object_label = serializers.SerializerMethodField()
    set_by_name = serializers.CharField(source='set_by.get_full_name', read_only=True)

    class Meta:
        model = CustomFieldValue
        fields = '__all__'
        read_only_fields = ('value_search', 'set_by', 'created_at', 'updated_at')

    def get_content_type_label(self, obj):
        return f'{obj.content_type.app_label}.{obj.content_type.model}' if obj.content_type_id else ''

    def get_content_object_label(self, obj):
        return str(obj.content_object) if obj.content_object else ''

    def validate(self, attrs):
        field = attrs.get('field') or getattr(self.instance, 'field', None)
        content_type = attrs.get('content_type') or getattr(self.instance, 'content_type', None)
        value = attrs.get('value', getattr(self.instance, 'value', None))

        if not field:
            raise serializers.ValidationError({'field': 'Field is required.'})
        if not content_type:
            raise serializers.ValidationError({'content_type': 'Content type is required.'})
        if field.content_type_id and content_type.id != field.content_type_id:
            expected = ContentType.objects.get(pk=field.content_type_id)
            raise serializers.ValidationError({'content_type': f'Field belongs to {expected.app_label}.{expected.model}.'})
        if field.is_required and empty_value(value):
            raise serializers.ValidationError({'value': 'This custom field is required.'})

        attrs['value'] = normalize_field_value(field, value)
        return attrs
