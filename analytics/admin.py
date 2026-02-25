# analytics/admin.py
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display, action
from django.contrib import messages
from django.shortcuts import redirect

from .models import Deal, Payment, Expense, FinancialPeriod, TransactionHistory
from .services import BillingService

class PaymentInline(TabularInline):
    model = Payment
    extra = 0
    tab = True
    verbose_name_plural = "История платежей"
    fields = ('amount', 'currency', 'exchange_rate', 'amount_usd', 'net_income_usd', 'payment_date', 'method', 'is_confirmed')
    readonly_fields = ('amount_usd', 'exchange_rate', 'is_confirmed') 

@admin.register(Deal)
class DealAdmin(ModelAdmin):
    change_form_template = "admin/analytics/deal/change_form.html"
    
    inlines = [PaymentInline]
    list_display = ("id", "display_client", "deal_type", "display_service_info", "display_financials", "payment_status_badge", "manager", "created_at")
    list_filter = ("payment_status", "deal_type", "created_at")
    search_fields = ("client__full_name", "id")
    list_per_page = 20

    list_select_related = ("client", "manager", "university", "service_ref", "program")
    autocomplete_fields = ["client", "manager", "university", "program", "service_ref"]

    fieldsets = (
        (_("Участники"), {
            "fields": ("client", "manager", "deal_type"),
            "classes": ("tab-tabular",),
        }),
        (_("Услуга"), {
            "fields": (("university", "program"), ("service_ref", "custom_service_name")),
            "classes": ("collapse",),
        }),
        (_("Финансы"), {
            "fields": (("price_client", "currency"), ("total_to_pay_usd", "expected_revenue_usd")),
            "classes": ("tab-tabular",),
        }),
        (_("Статус"), {
            "fields": ("payment_status", "paid_amount_usd"),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(manager=request.user)

    def get_changeform_initial_data(self, request):
        return {'manager': request.user}

    @display(description="Клиент")
    def display_client(self, obj):
        return obj.client.full_name

    @display(description="Услуга")
    def display_service_info(self, obj):
        if obj.deal_type == 'university' and obj.university:
            return f"{obj.university.name}"
        elif obj.deal_type == 'service':
            return obj.service_ref.title if obj.service_ref else obj.custom_service_name
        return "Не указано"

    @display(description="Финансы", label=True)
    def display_financials(self, obj):
        color = "success" if obj.paid_amount_usd >= obj.total_to_pay_usd else "warning"
        return f"${obj.paid_amount_usd:,.2f} / ${obj.total_to_pay_usd:,.2f}", color

    @display(description="Статус", label=True)
    def payment_status_badge(self, obj):
        colors = {'new': 'blue', 'paid_full': 'green', 'paid_partial': 'yellow', 'closed': 'gray'}
        return obj.get_payment_status_display(), colors.get(obj.payment_status, 'blue')


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ("deal", "manager", "display_amount", "amount_usd", "net_income_badge", "date_fmt", "is_confirmed")
    list_filter = ("is_confirmed", "payment_date", "method")
    search_fields = ("deal__client__full_name",)
    actions = ["confirm_payments"]
    
    list_select_related = ("deal", "manager", "currency", "deal__client")
    
    # ИСПРАВЛЕНИЕ: Блокируем галочку от ручного нажатия. Теперь ТОЛЬКО через Actions
    readonly_fields = ('amount_usd', 'exchange_rate', 'is_confirmed', 'confirmed_by', 'confirmed_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(manager=request.user)

    @action(description="✅ Подтвердить платежи и начислить бонусы")
    def confirm_payments(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, "У вас нет прав для этой операции", messages.ERROR)
            return 
        
        processed_count = 0
        for payment in queryset:
            if not payment.is_confirmed:
                BillingService.confirm_payment(payment, request.user)
                processed_count += 1
        
        self.message_user(request, f"Успешно подтверждено: {processed_count}. Бонусы начислены.", messages.SUCCESS)

    @display(description="Сумма")
    def display_amount(self, obj):
        return f"{obj.amount:,.2f} {obj.currency.code}"

    @display(description="Доход (USD)", label=True)
    def net_income_badge(self, obj):
        return f"+${obj.net_income_usd:,.2f}", "success"

    @display(description="Дата")
    def date_fmt(self, obj):
        return obj.payment_date.strftime("%d.%m")


@admin.register(TransactionHistory)
class TransactionHistoryAdmin(ModelAdmin):
    list_display = ("manager", "amount", "created_at", "description")
    list_filter = ("created_at", "manager")
    list_select_related = ("manager", "reference_payment")
    
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ("title", "amount_usd", "manager", "date")
    list_select_related = ("manager", "currency")
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(manager=request.user)


@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(ModelAdmin):
    list_display = ("period_name", "display_revenue", "display_profit", "is_closed", "status_badge")
    list_filter = ("is_closed",)
    actions = ["recalculate_period"]
    
    fieldsets = (
        ("Период", {
            "fields": (("start_date", "end_date"), "is_closed"),
            "classes": ("tab-tabular",),
        }),
        ("Финансы (Снапшот)", {
            "fields": (("total_revenue", "total_expenses"), "net_profit"),
            "classes": ("tab-tabular", "!bg-gray-50"),
            "description": "Данные обновляются кнопкой 'Пересчитать' или при закрытии периода."
        }),
    )
    readonly_fields = ("total_revenue", "total_expenses", "net_profit")

    def changelist_view(self, request, extra_context=None):
        FinancialPeriod.ensure_current_period()
        return super().changelist_view(request, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        
        if obj:
            from django.db.models import Sum
            from users.models import User
            from clients.models import Client
            from timetracking.models import WorkShift
            
            stats = obj.calculate_stats() 
            stats['total_new_clients'] = Client.objects.filter(created_at__date__range=(obj.start_date, obj.end_date)).count()
            
            leaderboard = []
            managers = User.objects.filter(managersalary__isnull=False)
            
            for m in managers:
                deals = m.deal_set.filter(created_at__date__range=(obj.start_date, obj.end_date))
                payments = m.payment_set.filter(payment_date__range=(obj.start_date, obj.end_date), is_confirmed=True)
                
                raised = payments.aggregate(Sum('amount_usd'))['amount_usd__sum'] or 0
                net = payments.aggregate(Sum('net_income_usd'))['net_income_usd__sum'] or 0
                forgets = WorkShift.objects.filter(employee=m, date__range=(obj.start_date, obj.end_date), is_auto_closed=True).count()
                
                if deals.count() > 0 or raised > 0 or forgets > 0:
                    leaderboard.append({
                        'name': f"{m.first_name} {m.last_name}",
                        'clients_count': Client.objects.filter(manager=m, created_at__date__range=(obj.start_date, obj.end_date)).count(),
                        'deals_count': deals.count(),
                        'total_raised': float(raised),
                        'net_income': float(net),
                        'forgets': forgets
                    })
            
            leaderboard.sort(key=lambda x: x['total_raised'], reverse=True)
            stats['leaderboard'] = leaderboard
            extra_context['report_stats'] = stats

        return super().change_view(request, object_id, form_url, extra_context)

    @action(description="🔄 Пересчитать статистику периода")
    def recalculate_period(self, request, queryset):
        for period in queryset:
            period.calculate_stats()
        self.message_user(request, "Статистика успешно обновлена.", messages.SUCCESS)

    @display(description="Период")
    def period_name(self, obj):
        return f"{obj.start_date.strftime('%d.%m')} - {obj.end_date.strftime('%d.%m.%Y')}"

    @display(description="Выручка", label=True)
    def display_revenue(self, obj):
        return f"${obj.total_revenue:,.2f}", "info"

    @display(description="Прибыль (Котёл)", label=True)
    def display_profit(self, obj):
        return f"${obj.net_profit:,.2f}", "success" if obj.net_profit > 0 else "danger"

    @display(description="Статус", label=True)
    def status_badge(self, obj):
        if obj.is_closed:
            return "Закрыт / Выплачено", "success"
        return "Активен", "warning"
    
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_module_permission(self, request):
        return request.user.is_superuser
    
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
from unfold.admin import ModelAdmin
from unfold.decorators import display
from .models import AuditLog 

@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ("action_time", "user", "action_flag_badge", "content_type", "object_repr", "change_message")
    list_filter = ("action_flag", "content_type", "user")
    search_fields = ("object_repr", "change_message")
    date_hierarchy = "action_time"
    ordering = ("-action_time",)

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    def has_module_permission(self, request):
        return request.user.is_superuser

    @display(description="Действие", label=True)
    def action_flag_badge(self, obj):
        if obj.action_flag == ADDITION:
            return "Создание", "success"
        elif obj.action_flag == CHANGE:
            return "Изменение", "warning"
        elif obj.action_flag == DELETION:
            return "Удаление", "danger"
        return "Другое", "default"