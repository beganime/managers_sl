from rest_framework import serializers

from catalog.models import Currency
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
        extra_kwargs = {
            'office': {'required': False, 'allow_null': True},
            'currency': {'required': False, 'allow_null': True},
            'category': {'required': False, 'allow_blank': True},
            'comment': {'required': False, 'allow_blank': True},
        }

    def get_created_by_name(self, obj):
        user = getattr(obj, 'created_by', None)
        if not user:
            return None
        return f'{user.first_name} {user.last_name}'.strip() or user.email

    def _is_admin(self, user):
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or getattr(user, 'role', None) == 'admin')
        )

    def _get_default_currency(self):
        usd = Currency.objects.filter(code__iexact='USD').first()
        if usd:
            return usd
        return Currency.objects.order_by('id').first()

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        office = attrs.get('office') or getattr(self.instance, 'office', None)
        if not office and request and not self._is_admin(user):
            office = (
                getattr(getattr(user, 'access_profile', None), 'managed_office', None)
                or getattr(user, 'office', None)
            )
            if office:
                attrs['office'] = office

        if not office:
            raise serializers.ValidationError({'office': 'Нужно указать офис'})

        currency = attrs.get('currency') or getattr(self.instance, 'currency', None)
        if not currency:
            currency = self._get_default_currency()
            if currency:
                attrs['currency'] = currency

        if not attrs.get('currency'):
            raise serializers.ValidationError(
                {'currency': 'Не найдена валюта по умолчанию. Создай USD в каталоге.'}
            )

        return attrs