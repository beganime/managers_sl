"""Read-only production smoke for the mobile admission-status contract.

Run inside the ManagerSL web container. Prints no client identifiers or data.
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'students_life.settings')

import django

django.setup()

from django.conf import settings
from django.test import RequestFactory

from apps.crm.views import ClientAdmissionStatusServiceView


key = settings.STUDENTS_LIFE_API_KEY or settings.LEADS_API_KEY
request = RequestFactory().get(
    '/api/internal/client/admissions/',
    {'mobile_user_id': 999999999},
    HTTP_X_API_KEY=key,
)
synthetic_client = SimpleNamespace(
    sl_id='SL-TEST', full_name='Synthetic Client', status='documents',
    updated_at=None, get_status_display=lambda: 'Сбор документов',
)
with patch('apps.crm.views.Client.objects.filter') as clients, patch('apps.crm.views.Application.objects.filter') as applications:
    clients.return_value.first.return_value = synthetic_client
    applications.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = []
    response = ClientAdmissionStatusServiceView.as_view()(request)
    client = response.data.get('client') or {}
    expected = {'sl_id', 'full_name', 'status', 'status_label', 'updated_at'}
    assert response.status_code == 200 and expected.issubset(client), 'Invalid status response'
    print('Admission-status contract: OK')
