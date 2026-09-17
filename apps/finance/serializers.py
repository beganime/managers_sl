from rest_framework import serializers
from .entry_service import entry_currency

from .models import (
    Cashbox,
    Deal,
    EmployeeCommission,
    Expense,
    ExpenseCategory,
    FinancialPeriod,
    Income,
    Payment,
    Transaction,
)


class CashboxSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = Cashbox
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class DealSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    service_title = serializers.CharField(source='service.title', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    deal_type_display = serializers.CharField(source='get_deal_type_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = Deal
        fields = '__all__'
        read_only_fields = ('total_to_pay_usd', 'paid_amount_usd', 'created_at', 'updated_at')


class EntrySerializer(serializers.ModelSerializer):
    entry_currency = serializers.ChoiceField(choices=('TMT', 'USD'), write_only=True, required=False)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Сумма должна быть больше нуля.')
        return value

    def validate_comment(self, value):
        if len(value) > 1000:
            raise serializers.ValidationError('Не более 1000 символов.')
        return value

    def validate_proof_file(self, value):
        if value and value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError('Максимальный размер файла — 50 МБ.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        currency = attrs.get('currency')
        code = attrs.pop('entry_currency', None)
        if currency and currency.code not in ('TMT', 'USD'):
            raise serializers.ValidationError({'currency': 'Выберите TMT или USD.'})
        if currency and code and currency.code != code:
            raise serializers.ValidationError({'currency': 'Валюта и код валюты должны совпадать.'})
        attrs['currency'] = entry_currency(code or (currency.code if currency else 'TMT'))
        return attrs


ENTRY_READ_ONLY = (
    'company', 'cashbox', 'employee', 'exchange_rate', 'amount_usd', 'amount_tmt',
    'is_confirmed', 'confirmed_by', 'confirmed_at', 'created_at', 'updated_at',
)


class PaymentSerializer(EntrySerializer):
    proof_file = serializers.FileField(required=True, allow_null=False)
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    deal_title = serializers.CharField(source='deal.title', read_only=True)
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    method_display = serializers.CharField(source='get_method_display', read_only=True)
    confirmed_by_name = serializers.CharField(source='confirmed_by.get_full_name', read_only=True)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ENTRY_READ_ONLY + ('client', 'manager')
        extra_kwargs = {'currency': {'required': False}, 'office': {'required': False}}


class ExpenseCategorySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ExpenseSerializer(EntrySerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    confirmed_by_name = serializers.CharField(source='confirmed_by.get_full_name', read_only=True)

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ENTRY_READ_ONLY
        extra_kwargs = {'currency': {'required': False}, 'office': {'required': False}, 'category': {'required': False, 'allow_null': True}}


class IncomeSerializer(EntrySerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    deal_title = serializers.CharField(source='deal.title', read_only=True)
    service_title = serializers.CharField(source='service.title', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    status_display = serializers.SerializerMethodField()

    def get_status_display(self, obj):
        return {'pending': 'На проверке', 'confirmed': 'Учтён', 'rejected': 'Отклонён'}.get(obj.status, obj.status)

    class Meta:
        model = Income
        fields = '__all__'
        read_only_fields = ENTRY_READ_ONLY + ('status', 'rejected_by', 'rejected_at', 'rejection_reason', 'client', 'deal', 'service')
        extra_kwargs = {'currency': {'required': False}, 'office': {'required': False}}


class TransactionSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()

    def get_title(self, obj):
        if obj.related_income_id:
            return obj.related_income.title
        if obj.related_expense_id:
            return obj.related_expense.title
        if obj.related_payment_id:
            return 'Оплата: ' + obj.related_payment.deal.title
        return obj.comment or 'Финансовая операция'
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    transaction_type_display = serializers.SerializerMethodField()

    def get_transaction_type_display(self, obj):
        return {'income': 'Пополнение офиса', 'expense': 'Расход', 'payment': 'Оплата договора',
                'transfer_in': 'Входящий перевод', 'transfer_out': 'Исходящий перевод',
                'correction': 'Корректировка'}.get(obj.transaction_type, obj.transaction_type)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class EmployeeCommissionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    deal_title = serializers.CharField(source='deal.title', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)

    class Meta:
        model = EmployeeCommission
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class FinancialPeriodSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    closed_by_name = serializers.CharField(source='closed_by.get_full_name', read_only=True)

    class Meta:
        model = FinancialPeriod
        fields = '__all__'
        read_only_fields = (
            'total_revenue_usd',
            'total_expenses_usd',
            'net_profit_usd',
            'is_closed',
            'closed_by',
            'closed_at',
            'created_at',
            'updated_at',
        )
