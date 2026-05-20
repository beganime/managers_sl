from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CashboxViewSet,
    DealViewSet,
    EmployeeCommissionViewSet,
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    FinancialPeriodViewSet,
    IncomeViewSet,
    PaymentViewSet,
    TransactionViewSet,
)

router = DefaultRouter()
router.register('cashboxes', CashboxViewSet, basename='finance-cashbox')
router.register('deals', DealViewSet, basename='finance-deal')
router.register('payments', PaymentViewSet, basename='finance-payment')
router.register('expense-categories', ExpenseCategoryViewSet, basename='finance-expense-category')
router.register('expenses', ExpenseViewSet, basename='finance-expense')
router.register('incomes', IncomeViewSet, basename='finance-income')
router.register('transactions', TransactionViewSet, basename='finance-transaction')
router.register('commissions', EmployeeCommissionViewSet, basename='finance-commission')
router.register('periods', FinancialPeriodViewSet, basename='finance-period')

urlpatterns = [
    path('', include(router.urls)),
]
