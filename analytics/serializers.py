# analytics/serializers.py
from decimal import Decimal
import datetime
from django.db.models import Sum
from rest_framework import serializers

from .models import Deal, Payment, Expense, FinancialPeriod
from users.models import User
from clients.models import Client


def is_admin_user(user):
    return bool(
        user and user.is_authenticated and (
            user.is_superuser or getattr(user, 'role', None) == 'admin'
        )
    )


class SafeDateField(serializers.DateField):
    def to_representation(self, value):
        if isinstance(value, datetime.datetime):
            value = value.date()
        return super().to_representation(value)


class SimpleUserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'full_name')

    def get_full_name(self, obj):
        full = f"{obj.first_name} {obj.last_name}".strip()
        return full or obj.email


class SimpleClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ('id', 'full_name', 'phone', 'city', 'status')


class PaymentLiteSerializer(serializers.ModelSerializer):
    payment_date = SafeDateField(read_only=True)

    class Meta:
        model = Payment
        fields = (
            'id',
            'amount',
            'amount_usd',
            'payment_date',
            'method',
            'is_confirmed',
            'updated_at',
        )


class DealShortSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.full_name', read_only=True)

    class Meta:
        model = Deal
        fields = (
            'id',
            'client_name',
            'deal_type',
            'total_to_pay_usd',
            'paid_amount_usd',
            'payment_status',
        )


class DealSerializer(serializers.ModelSerializer):
    client_data = SimpleClientSerializer(source='client', read_only=True)
    manager_data = SimpleUserSerializer(source='manager', read_only=True)
    payments = PaymentLiteSerializer(many=True, read_only=True)

    university_name = serializers.CharField(source='university.name', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True)
    service_title = serializers.CharField(source='service_ref.title', read_only=True)

    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Deal
        fields = (
            'id',
            'client',
            'client_data',
            'manager',
            'manager_data',
            'deal_type',
            'university',
            'university_name',
            'program',
            'program_name',
            'service_ref',
            'service_title',
            'custom_service_name',
            'custom_service_desc',
            'currency',
            'price_client',
            'expected_revenue_usd',
            'total_to_pay_usd',
            'paid_amount_usd',
            'payment_status',
            'payments',
            'created_at',
            'updated_at',
        )
        read_only_fields = (
            'expected_revenue_usd',
            'total_to_pay_usd',
            'paid_amount_usd',
            'payment_status',
            'created_at',
            'updated_at',
        )

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        instance = getattr(self, 'instance', None)
        is_admin = is_admin_user(user)

        client = attrs.get('client') or (instance.client if instance else None)
        manager = attrs.get('manager') or (instance.manager if instance else None)
        deal_type = attrs.get('deal_type') or (instance.deal_type if instance else None)
        university = attrs.get('university') or (instance.university if instance else None)
        program = attrs.get('program') or (instance.program if instance else None)
        service_ref = attrs.get('service_ref') or (instance.service_ref if instance else None)
        custom_service_name = attrs.get('custom_service_name')
        if custom_service_name is None and instance:
            custom_service_name = instance.custom_service_name
        currency = attrs.get('currency') or (instance.currency if instance else None)
        price_client = attrs.get('price_client')
        if price_client is None and instance:
            price_client = instance.price_client

        if not client:
            raise serializers.ValidationError({'client': 'Нужно указать клиента.'})

        if price_client is None or price_client <= 0:
            raise serializers.ValidationError({'price_client': 'Цена для клиента должна быть больше нуля.'})

        if not is_admin:
            if client.manager_id != user.id and not client.shared_with.filter(id=user.id).exists():
                raise serializers.ValidationError({
                    'client': 'Менеджер не может создавать сделку по чужому клиенту.'
                })
            attrs['manager'] = user
        else:
            if not manager:
                attrs['manager'] = client.manager
                manager = client.manager
            if not manager:
                raise serializers.ValidationError({
                    'manager': 'Для сделки нужно указать менеджера.'
                })

        if not currency:
            raise serializers.ValidationError({'currency': 'Нужно указать валюту сделки.'})

        if currency.rate <= 0:
            raise serializers.ValidationError({'currency': 'Курс валюты должен быть больше нуля.'})

        if deal_type == 'university':
            if not university:
                raise serializers.ValidationError({'university': 'Для поступления нужно указать ВУЗ.'})
            if not program:
                raise serializers.ValidationError({'program': 'Для поступления нужно указать программу.'})
            if program and university and program.university_id != university.id:
                raise serializers.ValidationError({'program': 'Программа не принадлежит выбранному университету.'})

            attrs['service_ref'] = None
            attrs['custom_service_name'] = ''
            attrs['custom_service_desc'] = ''

        elif deal_type == 'service':
            if not service_ref and not str(custom_service_name or '').strip():
                raise serializers.ValidationError({
                    'service_ref': 'Укажите услугу из каталога или заполните custom_service_name.'
                })

            attrs['university'] = None
            attrs['program'] = None
            attrs['custom_service_name'] = str(attrs.get('custom_service_name') or '').strip()
            attrs['custom_service_desc'] = str(attrs.get('custom_service_desc') or '').strip()
        else:
            raise serializers.ValidationError({'deal_type': 'Некорректный тип сделки.'})

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None

        if not is_admin_user(user):
            validated_data['manager'] = user
        elif not validated_data.get('manager') and validated_data.get('client'):
            validated_data['manager'] = validated_data['client'].manager

        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context.get('request')
        user = request.user if request else None

        if not is_admin_user(user):
            validated_data.pop('manager', None)

        return super().update(instance, validated_data)


class PaymentSerializer(serializers.ModelSerializer):
    deal_data = DealShortSerializer(source='deal', read_only=True)
    manager_data = SimpleUserSerializer(source='manager', read_only=True)
    payment_date = SafeDateField(required=False)

    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Payment
        fields = (
            'id',
            'deal',
            'deal_data',
            'manager',
            'manager_data',
            'amount',
            'currency',
            'exchange_rate',
            'amount_usd',
            'net_income_usd',
            'payment_date',
            'method',
            'is_confirmed',
            'confirmed_by',
            'confirmed_at',
            'updated_at',
        )
        read_only_fields = (
            'exchange_rate',
            'amount_usd',
            'net_income_usd',
            'is_confirmed',
            'confirmed_by',
            'confirmed_at',
            'updated_at',
        )

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        instance = getattr(self, 'instance', None)
        is_admin = is_admin_user(user)

        deal = attrs.get('deal') or (instance.deal if instance else None)
        amount = attrs.get('amount')
        if amount is None and instance:
            amount = instance.amount
        currency = attrs.get('currency') or (instance.currency if instance else None)

        if instance and instance.is_confirmed:
            raise serializers.ValidationError('Подтверждённый платёж нельзя изменять через API.')

        if not deal:
            raise serializers.ValidationError({'deal': 'Нужно указать сделку.'})

        if not is_admin and deal.manager_id != user.id:
            raise serializers.ValidationError({
                'deal': 'Менеджер не может создавать платёж по чужой сделке.'
            })

        if amount is None or amount <= 0:
            raise serializers.ValidationError({'amount': 'Сумма платежа должна быть больше нуля.'})

        if not currency:
            raise serializers.ValidationError({'currency': 'Нужно указать валюту платежа.'})

        if currency.rate <= 0:
            raise serializers.ValidationError({'currency': 'Курс валюты должен быть больше нуля.'})

        incoming_amount_usd = amount if currency.code == 'USD' else (amount / currency.rate)

        existing_total_usd = (
            deal.payments.exclude(pk=instance.pk if instance else None)
            .aggregate(total=Sum('amount_usd'))
            .get('total') or Decimal('0.00')
        )

        limit = deal.total_to_pay_usd or Decimal('0.00')
        if existing_total_usd + incoming_amount_usd > limit + Decimal('0.01'):
            raise serializers.ValidationError({
                'amount': f'Платёж превышает остаток по сделке. Осталось максимум ${max(limit - existing_total_usd, Decimal("0.00")):.2f}.'
            })

        if not attrs.get('payment_date'):
            from django.utils import timezone
            attrs['payment_date'] = timezone.localdate()

        if not is_admin:
            attrs['manager'] = user
        elif not attrs.get('manager'):
            attrs['manager'] = deal.manager

        return attrs