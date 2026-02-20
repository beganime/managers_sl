from django.urls import path
from .views import LeadCreateAPIView

urlpatterns = [
    # Эндпоинт будет доступен по адресу: /api/leads/create/
    path('api/leads/create/', LeadCreateAPIView.as_view(), name='lead-create'),
]