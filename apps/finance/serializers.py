from rest_framework import serializers

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


class PaymentSerializer(serializers.ModelSerializer):
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
        read_only_fields = ('amount_usd', 'is_confirmed', 'confirmed_by', 'confirmed_at', 'created_at', 'updated_at')


class ExpenseCategorySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ExpenseSerializer(serializers.ModelSerializer):
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
        read_only_fields = ('amount_usd', 'is_confirmed', 'confirmed_by', 'confirmed_at', 'created_at', 'updated_at')


class IncomeSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    deal_title = serializers.CharField(source='deal.title', read_only=True)
    service_title = serializers.CharField(source='service.title', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Income
        fields = '__all__'
        read_only_fields = ('amount_usd', 'is_confirmed', 'confirmed_by', 'confirmed_at', 'rejected_by', 'rejected_at', 'created_at', 'updated_at')


class TransactionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)
    cashbox_name = serializers.CharField(source='cashbox.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
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
