from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.core.permissions import get_employee_profile, is_erp_admin

from .models import Service, ServiceCategory, ServicePrice


def can_view_real_cost(user):
    if is_erp_admin(user):
        return True

    employee = get_employee_profile(user)
    if not employee:
        return False

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None
    return role_type == 'accountant' or bool(access and access.can_manage_finance)


class HideRealCostMixin:
    real_cost_fields = ('real_cost',)

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if can_view_real_cost(request.user):
            return fields
        return [field for field in fields if field not in self.real_cost_fields]

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if can_view_real_cost(request.user):
            return readonly_fields
        return readonly_fields + [field for field in self.real_cost_fields if field not in readonly_fields]


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(ModelAdmin):
    list_display = ('name', 'code', 'company', 'sort_order', 'is_active')
    list_filter = ('is_active', 'company')
    search_fields = ('name', 'code', 'description', 'company__name')
    autocomplete_fields = ('company',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Service)
class ServiceAdmin(HideRealCostMixin, ModelAdmin):
    list_display = ('title', 'code', 'category', 'company', 'price_client', 'currency', 'is_public', 'is_active')
    list_filter = ('is_active', 'is_public', 'company', 'category', 'currency')
    search_fields = ('title', 'code', 'description', 'category__name', 'company__name')
    autocomplete_fields = ('company', 'category', 'currency')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ServicePrice)
class ServicePriceAdmin(HideRealCostMixin, ModelAdmin):
    list_display = ('service', 'currency', 'price_client', 'valid_from', 'valid_to', 'updated_at')
    list_filter = ('currency', 'valid_from', 'valid_to', 'service__company', 'service__category')
    search_fields = ('service__title', 'service__code', 'currency__code', 'notes')
    autocomplete_fields = ('service', 'currency')
    readonly_fields = ('created_at', 'updated_at')

