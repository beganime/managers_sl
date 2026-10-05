from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.portal.views import DashboardDiskUsageView


class DashboardDiskUsageTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/portal/dashboard/disk-usage/')
        self.request.user = SimpleNamespace(is_authenticated=True)

    @patch('apps.portal.views.dashboard_disk_usage')
    @patch('apps.portal.views.can_access_disk', return_value=False)
    def test_denies_users_without_disk_access(self, _allowed, usage):
        response = DashboardDiskUsageView.as_view()(self.request)

        self.assertEqual(response.status_code, 403)
        usage.assert_not_called()

    @patch('apps.portal.views.dashboard_disk_usage', return_value=None)
    @patch('apps.portal.views.can_access_disk', return_value=True)
    def test_reports_unavailable_storage_without_fake_numbers(self, _allowed, _usage):
        response = DashboardDiskUsageView.as_view()(self.request)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Cache-Control'], 'no-store, private')

    @patch('apps.portal.views.dashboard_disk_usage', return_value={
        'used': '1 ГБ', 'free': '9 ГБ', 'total': '10 ГБ', 'percent': 10.0,
    })
    @patch('apps.portal.views.can_access_disk', return_value=True)
    def test_returns_usage_for_authorized_user(self, _allowed, _usage):
        response = DashboardDiskUsageView.as_view()(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'9', response.content)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
