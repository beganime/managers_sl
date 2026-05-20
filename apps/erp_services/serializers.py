from rest_framework import serializers

from apps.core.permissions import get_employee_profile, is_erp_admin

from .models import Service, ServiceCategory, ServicePrice


def can_view_real_cost(request):
    user = getattr(request, 'user', None)
    if is_erp_admin(user):
        return True

    employee = get_employee_profile(user)
    if not employee:
        return False

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None
    return role_type == 'accountant' or bool(access and access.can_manage_finance)


class HideRealCostSerializerMixin:
    def get_fields(self):
        fields = super().get_fields()
        if can_view_real_cost(self.context.get('request')):
            return fields
        fields.pop('real_cost', None)
        return fields


class ServiceCategorySerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ServiceCategory
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ServicePriceSerializer(HideRealCostSerializerMixin, serializers.ModelSerializer):
    service_title = serializers.CharField(source='service.title', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    currency_symbol = serializers.CharField(source='currency.symbol', read_only=True)

    class Meta:
        model = ServicePrice
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class ServiceSerializer(HideRealCostSerializerMixin, serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    currency_symbol = serializers.CharField(source='currency.symbol', read_only=True)
    prices = ServicePriceSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

