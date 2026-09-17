from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    Cashbox,
    Deal,
    DealAdditionalService,
    EmployeeBalance,
    EmployeeCommission,
    Expense,
    ExpenseCategory,
    FinancialPeriod,
    Income,
    FinanceSettings,
    Payment,
    Transaction,
)


class DealAdditionalServiceInline(admin.TabularInline):
    model = DealAdditionalService
    extra = 0
    autocomplete_fields = ('currency', 'created_by')
    readonly_fields = ('amount_usd', 'created_at', 'updated_at')


@admin.register(FinanceSettings)
class FinanceSettingsAdmin(ModelAdmin):
    list_display = ('usd_to_tmt', 'updated_by', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not FinanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(EmployeeBalance)
class EmployeeBalanceAdmin(ModelAdmin):
    list_display = ('employee', 'office', 'balance_tmt', 'updated_at')
    list_filter = ('office',)
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__email', 'office__name')
    autocomplete_fields = ('employee', 'office')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Cashbox)
class CashboxAdmin(ModelAdmin):
    list_display = ('name', 'company', 'office', 'currency', 'balance', 'is_active')
    list_filter = ('is_active', 'company', 'office', 'currency')
    search_fields = ('name', 'company__name', 'office__name', 'office__city')
    autocomplete_fields = ('company', 'office', 'currency')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Deal)
class DealAdmin(ModelAdmin):
    list_display = ('contract_number', 'title', 'client', 'manager', 'company', 'office', 'contract_date', 'payment_due_date', 'payment_status', 'total_to_pay_usd', 'paid_amount_usd')
    list_filter = ('payment_status', 'deal_type', 'company', 'office', 'manager', 'created_at')
    search_fields = ('contract_number', 'title', 'client__full_name', 'client__sl_id', 'client__phone', 'university_name', 'program_name', 'service__title')
    autocomplete_fields = ('company', 'office', 'client', 'application', 'manager', 'service', 'currency')
    readonly_fields = ('total_to_pay_usd', 'paid_amount_usd', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'
    inlines = (DealAdditionalServiceInline,)


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ('client', 'deal', 'amount', 'currency', 'amount_usd', 'amount_tmt', 'method', 'payment_date', 'has_proof', 'is_confirmed')
    list_filter = ('is_confirmed', 'method', 'company', 'office', 'cashbox', 'payment_date')
    search_fields = ('client__full_name', 'client__phone', 'deal__title', 'comment')
    autocomplete_fields = ('company', 'office', 'deal', 'client', 'manager', 'cashbox', 'currency', 'confirmed_by')
    readonly_fields = ('amount_usd', 'confirmed_at', 'created_at', 'updated_at')
    date_hierarchy = 'payment_date'

    @admin.display(boolean=True, description='Proof')
    def has_proof(self, obj):
        return bool(obj.proof_file)

    @admin.action(description='Подтвердить выбранные платежи')
    def confirm_payments(self, request, queryset):
        for payment in queryset.select_related('deal', 'cashbox', 'currency'):
            payment.confirm(user=request.user)

    actions = ('confirm_payments',)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(ModelAdmin):
    list_display = ('name', 'code', 'company', 'is_active')
    list_filter = ('is_active', 'company')
    search_fields = ('name', 'code', 'company__name')
    autocomplete_fields = ('company',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ('title', 'category', 'amount', 'currency', 'amount_usd', 'amount_tmt', 'date', 'company', 'office', 'has_proof', 'is_confirmed')
    list_filter = ('is_confirmed', 'category', 'company', 'office', 'date')
    search_fields = ('title', 'comment', 'employee__email', 'category__name')
    autocomplete_fields = ('company', 'office', 'category', 'employee', 'cashbox', 'currency', 'confirmed_by')
    readonly_fields = ('amount_usd', 'confirmed_at', 'created_at', 'updated_at')
    date_hierarchy = 'date'

    @admin.display(boolean=True, description='Proof')
    def has_proof(self, obj):
        return bool(obj.proof_file)

    @admin.action(description='Подтвердить выбранные расходы')
    def confirm_expenses(self, request, queryset):
        for expense in queryset.select_related('cashbox', 'currency'):
            expense.confirm(user=request.user)

    actions = ('confirm_expenses',)


@admin.register(Income)
class IncomeAdmin(ModelAdmin):
    list_display = ('title', 'employee', 'amount', 'currency', 'amount_usd', 'amount_tmt', 'date', 'company', 'office', 'status', 'is_confirmed')
    list_filter = ('status', 'is_confirmed', 'company', 'office', 'cashbox', 'currency', 'date')
    search_fields = ('title', 'source', 'comment', 'employee__email', 'client__full_name', 'deal__title', 'service__title')
    autocomplete_fields = ('company', 'office', 'cashbox', 'employee', 'client', 'deal', 'service', 'currency', 'confirmed_by', 'rejected_by')
    readonly_fields = ('amount_usd', 'confirmed_at', 'rejected_at', 'created_at', 'updated_at')
    date_hierarchy = 'date'

    @admin.action(description='Подтвердить выбранные доходы')
    def confirm_incomes(self, request, queryset):
        for income in queryset.select_related('cashbox', 'currency', 'employee'):
            income.confirm(user=request.user)

    @admin.action(description='Отклонить выбранные доходы')
    def reject_incomes(self, request, queryset):
        for income in queryset.select_related('cashbox', 'currency', 'employee'):
            income.reject(user=request.user, reason='Rejected from admin action.')

    actions = ('confirm_incomes', 'reject_incomes')


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    list_display = ('transaction_type', 'cashbox', 'amount', 'currency', 'amount_usd', 'amount_tmt', 'company', 'office', 'created_by', 'created_at')
    list_filter = ('transaction_type', 'company', 'office', 'cashbox', 'currency', 'created_at')
    search_fields = ('comment', 'related_payment__client__full_name', 'related_expense__title', 'related_income__title')
    autocomplete_fields = ('company', 'office', 'cashbox', 'currency', 'related_payment', 'related_expense', 'related_income', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(EmployeeCommission)
class EmployeeCommissionAdmin(ModelAdmin):
    list_display = ('employee', 'deal', 'payment', 'income', 'percent', 'amount_usd', 'status', 'company', 'office')
    list_filter = ('status', 'company', 'office', 'employee', 'created_at')
    search_fields = ('employee__email', 'deal__title', 'payment__client__full_name', 'income__title')
    autocomplete_fields = ('company', 'office', 'employee', 'payment', 'income', 'deal', 'approved_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(ModelAdmin):
    list_display = ('company', 'office', 'start_date', 'end_date', 'total_revenue_usd', 'total_expenses_usd', 'net_profit_usd', 'is_closed')
    list_filter = ('is_closed', 'company', 'office', 'start_date', 'end_date')
    search_fields = ('company__name', 'office__name', 'office__city')
    autocomplete_fields = ('company', 'office', 'closed_by')
    readonly_fields = ('total_revenue_usd', 'total_expenses_usd', 'net_profit_usd', 'closed_at', 'created_at', 'updated_at')
    date_hierarchy = 'start_date'

    @admin.action(description='Calculate selected periods')
    def calculate_periods(self, request, queryset):
        for period in queryset:
            period.calculate()

    @admin.action(description='Close selected periods')
    def close_periods(self, request, queryset):
        for period in queryset:
            period.close(user=request.user)

    actions = ('calculate_periods', 'close_periods')
