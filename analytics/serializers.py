# analytics/serializers.py
from rest_framework import serializers
from .models import Deal, Payment, Expense

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('manager', 'exchange_rate', 'amount_usd', 'is_confirmed', 'confirmed_by', 'confirmed_at', 'updated_at')

class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ('manager', 'amount_usd', 'updated_at')

class DealSerializer(serializers.ModelSerializer):
    payments = PaymentSerializer(many=True, read_only=True)
    
    class Meta:
        model = Deal
        fields = '__all__'
        # ВАЖНО: Мы убрали 'total_to_pay_usd' из read_only, чтобы оно нормально сохранялось!
        read_only_fields = ('manager', 'paid_amount_usd', 'payment_status', 'created_at', 'updated_at')