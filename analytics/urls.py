from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .finance_views import OfficeFinanceEntryViewSet
from .views import DealViewSet, PaymentViewSet, ExpenseViewSet, FinancialPeriodViewSet

router = DefaultRouter()
router.register(r'deals', DealViewSet, basename='deal')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'periods', FinancialPeriodViewSet, basename='financial-period')
router.register(r'cashflow', OfficeFinanceEntryViewSet, basename='office-finance-entry')

urlpatterns = [
    path('analytics/', include(router.urls)),
]