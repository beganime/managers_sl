# analytics/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DealViewSet, PaymentViewSet, ExpenseViewSet

router = DefaultRouter()
router.register(r'deals', DealViewSet, basename='deal')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'expenses', ExpenseViewSet, basename='expense')

urlpatterns = [
    path('api/analytics/', include(router.urls)),
]