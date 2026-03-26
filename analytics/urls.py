# analytics/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import DealViewSet, PaymentViewSet, ExpenseViewSet, FinancialPeriodViewSet

router = DefaultRouter()
router.register(r'deals', DealViewSet, basename='deal')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'expenses', ExpenseViewSet, basename='expense')
router.register(r'periods', FinancialPeriodViewSet, basename='financial-period')

urlpatterns = [
    path('analytics/', include(router.urls)),
]