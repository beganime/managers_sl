from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.employees.models import EmployeeProfile, EmployeeRole
from apps.organizations.models import Company

from .disk_monitor import check_disk_health, format_bytes, storage_alert_level
from .models import AttendanceTelegramDelivery, EmployeeTelegramAccount


class DiskMonitorHelpersTests(TestCase):
    def test_storage_thresholds(self):
        self.assertIsNone(storage_alert_level(74.9))
        self.assertEqual(storage_alert_level(75), 'warning')
        self.assertEqual(storage_alert_level(90), 'high')
        self.assertEqual(storage_alert_level(95), 'critical')

    def test_formats_bytes(self):
        self.assertEqual(format_bytes(1024 ** 3), '1.0 ГБ')


@override_settings(
    ATTENDANCE_TELEGRAM_ENABLED=True,
    DISK_MONITOR_RECIPIENT_EMAIL='owner@example.com',
)
class DiskMonitorDeliveryTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name='Students Life')
        role = EmployeeRole.objects.create(code='owner', name='Owner', role_type='company_owner')
        owner = get_user_model().objects.create_user(email='owner@example.com', password='test')
        EmployeeProfile.objects.create(user=owner, company=company, role=role)
        EmployeeTelegramAccount.objects.create(
            employee=owner,
            telegram_user_id=101,
            chat_id=202,
        )

    @patch('apps.attendance.disk_monitor._enqueue')
    @patch('apps.attendance.disk_monitor._fetch_monitor_payload')
    def test_critical_quota_queues_personal_alert_once(self, fetch, enqueue):
        fetch.return_value = {
            'status': 'ok',
            'storage': {
                'usage_percent': 96,
                'used_bytes': 960,
                'free_bytes': 40,
                'total_bytes': 1000,
                'objects': 12,
                'age_seconds': 5,
            },
        }

        first = check_disk_health()
        second = check_disk_health()

        self.assertTrue(first['queued'])
        self.assertFalse(second['queued'])
        delivery = AttendanceTelegramDelivery.objects.get()
        self.assertEqual(delivery.target_chat_id, 202)
        self.assertIn('#критично_DiskSL', delivery.message)
        enqueue.assert_called_once()

    @patch('apps.attendance.disk_monitor._enqueue')
    @patch('apps.attendance.disk_monitor._fetch_monitor_payload')
    def test_healthy_summary_contains_configured_limit(self, fetch, enqueue):
        fetch.return_value = {
            'status': 'ok',
            'storage': {
                'usage_percent': 10,
                'used_bytes': 100,
                'free_bytes': 900,
                'total_bytes': 1000,
                'objects': 2,
                'age_seconds': 5,
            },
        }

        result = check_disk_health(send_summary=True)

        self.assertTrue(result['queued'])
        delivery = AttendanceTelegramDelivery.objects.get()
        self.assertIn('Настроенный лимит', delivery.message)
        enqueue.assert_called_once()
