from rest_framework import serializers

from users.models import Office
from .finance_models import OfficeFinanceEntry


class OfficeFinanceEntrySerializer(serializers.ModelSerializer):
    office_name = serializers.CharField(source='office.city', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = OfficeFinanceEntry
        fields = (
            'id',
            'office',
            'office_name',
            'created_by',
            'created_by_name',
            'entry_type',
            'title',
            'category',
            'comment',
            'amount',
            'currency',
            'currency_code',
            'exchange_rate',
            'amount_usd',
            'entry_date',
            'is_confirmed',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_by', 'amount_usd', 'created_at', 'updated_at')

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if not user:
            return None
        return f'{user.first_name} {user.last_name}'.strip() or user.email

    def validate(self, attrs):
        request = self.context.get('request')
        office = attrs.get('office') or getattr(self.instance, 'office', None)

        if not office and request and not request.user.is_superuser and getattr(request.user, 'role', None) != 'admin':
            office = request.user.office
            attrs['office'] = office

        if not office:
            raise serializers.ValidationError({'office': 'Нужно указать офис'})

        return attrs