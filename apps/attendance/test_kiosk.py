from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.employees.models import EmployeeProfile, EmployeeRole
from apps.organizations.models import Company, Office

from .kiosk import (
    build_badge_code,
    issue_badge,
    parse_device_time,
    process_checkin,
    regenerate_badge,
    resolve_badge,
)
from .models import CheckinEvent, KioskDevice, WorkDay


@override_settings(ATTENDANCE_WORKDAYS=(0, 1, 2, 3, 4, 5, 6), ATTENDANCE_AUTO_CLOSE_HOUR=20)
class KioskCheckinTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.office = Office.objects.create(company=self.company, name='Головной офис')
        self.role = EmployeeRole.objects.create(code='manager', name='Менеджер', role_type='manager')
        self.user = get_user_model().objects.create_user(
            email='kiosk-manager@example.com', password='test-password', first_name='Анна', last_name='Иванова',
        )
        EmployeeProfile.objects.create(user=self.user, company=self.company, office=self.office, role=self.role)
        self.device = KioskDevice.objects.create(name='Планшет у входа', office=self.office, token='device-token-123')
        self.badge = issue_badge(self.user)
        self.code = build_badge_code(self.badge)

    def post_checkin(self, code=None, event_id=None, device_time=None, token='device-token-123'):
        client = APIClient()
        payload = {'code': self.code if code is None else code, 'event_id': str(event_id or uuid4())}
        if device_time:
            payload['device_time'] = device_time.isoformat()
        if token is not None:
            client.credentials(HTTP_X_KIOSK_TOKEN=token)
        return client.post('/api/v1/attendance/kiosk/checkin/', payload, format='json')

    def test_badge_code_roundtrip(self):
        resolved = resolve_badge(self.code)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, self.badge.pk)

    def test_badge_code_rejects_tampered_token(self):
        parts = self.code.split('.')
        parts[2] = parts[2][:-2] + 'zz'
        self.assertIsNone(resolve_badge('.'.join(parts)))

    def test_regenerate_invalidates_old_code(self):
        regenerate_badge(self.user)
        self.assertIsNone(resolve_badge(self.code))
        badge = issue_badge(self.user)
        self.assertIsNotNone(resolve_badge(build_badge_code(badge)))

    def test_missing_device_token_is_rejected(self):
        response = self.post_checkin(token=None)
        self.assertIn(response.status_code, (401, 403))

    def test_wrong_device_token_is_rejected(self):
        response = self.post_checkin(token='wrong-token')
        self.assertIn(response.status_code, (401, 403))

    def test_first_scan_starts_workday(self):
        response = self.post_checkin()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['result'], CheckinEvent.RESULT_STARTED)
        workday = WorkDay.objects.get(employee=self.user, date=timezone.localdate())
        self.assertEqual(workday.status, WorkDay.STATUS_STARTED)
        self.assertIsNotNone(workday.started_at)
        self.assertTrue(workday.sessions.filter(is_active=True).exists())
        self.assertIn('Киоск', workday.sessions.first().start_note)

    def test_resending_same_event_is_idempotent(self):
        event_id = uuid4()
        first = self.post_checkin(event_id=event_id)
        second = self.post_checkin(event_id=event_id)
        self.assertTrue(first.data['created'])
        self.assertFalse(second.data['created'])
        workday = WorkDay.objects.get(employee=self.user, date=timezone.localdate())
        self.assertEqual(workday.sessions.count(), 1)
        self.assertEqual(CheckinEvent.objects.filter(event_uuid=event_id).count(), 1)

    def test_second_scan_closes_workday(self):
        self.post_checkin()
        response = self.post_checkin()
        self.assertEqual(response.data['result'], CheckinEvent.RESULT_CLOSED)
        workday = WorkDay.objects.get(employee=self.user, date=timezone.localdate())
        self.assertEqual(workday.status, WorkDay.STATUS_CLOSED)
        self.assertFalse(workday.sessions.filter(is_active=True).exists())

    def test_third_scan_reports_already_closed(self):
        self.post_checkin()
        self.post_checkin()
        response = self.post_checkin()
        self.assertEqual(response.data['result'], CheckinEvent.RESULT_ALREADY_CLOSED)
        self.assertEqual(WorkDay.objects.get(employee=self.user).status, WorkDay.STATUS_CLOSED)

    def test_invalid_code_is_recorded_without_workday(self):
        response = self.post_checkin(code='SL1.999999.not-a-token')
        self.assertEqual(response.data['result'], CheckinEvent.RESULT_INVALID_CODE)
        self.assertFalse(WorkDay.objects.filter(employee=self.user).exists())

    def test_untracked_admin_is_rejected(self):
        admin = get_user_model().objects.create_user(email='kiosk-admin@example.com', password='test-password', role='admin')
        EmployeeProfile.objects.create(user=admin, company=self.company, office=self.office, role=self.role)
        badge = issue_badge(admin)
        response = self.post_checkin(code=build_badge_code(badge))
        self.assertEqual(response.data['result'], CheckinEvent.RESULT_UNTRACKED)
        self.assertFalse(WorkDay.objects.filter(employee=admin).exists())

    def test_late_sync_is_flagged(self):
        past = timezone.now() - timedelta(hours=1)
        response = self.post_checkin(device_time=past)
        self.assertGreater(response.data['sync_delay_seconds'], 3000)
        self.assertIn('синхронизировано поздно', response.data['message'])
        event = CheckinEvent.objects.get(event_uuid=response.data['event_id'])
        self.assertGreater(event.sync_delay_seconds, 300)

    def test_naive_device_time_is_treated_as_utc(self):
        parsed = parse_device_time('2026-11-08T09:00:00')
        self.assertIsNotNone(parsed)
        self.assertTrue(timezone.is_aware(parsed))
        self.assertIsNone(parse_device_time('not-a-date'))

    def test_status_endpoint_returns_device_info(self):
        client = APIClient()
        client.credentials(HTTP_X_KIOSK_TOKEN='device-token-123')
        response = client.get('/api/v1/attendance/kiosk/checkin/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['device']['name'], 'Планшет у входа')
        self.assertEqual(response.data['device']['office'], 'Головной офис')
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen_at)

    def test_direct_process_checkin_creates_event(self):
        event, created = process_checkin(device=self.device, code=self.code, event_uuid=uuid4())
        self.assertTrue(created)
        self.assertEqual(event.result, CheckinEvent.RESULT_STARTED)


@override_settings(ATTENDANCE_WORKDAYS=(0, 1, 2, 3, 4, 5, 6), ATTENDANCE_AUTO_CLOSE_HOUR=20)
class KioskQrGeneratorTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.role = EmployeeRole.objects.create(code='manager', name='Менеджер', role_type='manager')
        self.user = get_user_model().objects.create_user(
            email='qr-manager@example.com', password='test-password', first_name='Берди', last_name='Мурадов',
        )
        EmployeeProfile.objects.create(user=self.user, company=self.company, role=self.role)
        self.admin = get_user_model().objects.create_user(
            email='qr-admin@example.com', password='test-password', role='admin',
        )

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get('/portal/kiosk-qr/')
        self.assertEqual(response.status_code, 302)

    def test_manager_without_admin_role_is_forbidden(self):
        self.client.force_login(self.user)
        response = self.client.get('/portal/kiosk-qr/')
        self.assertEqual(response.status_code, 403)

    def test_admin_sees_employee_selector(self):
        self.client.force_login(self.admin)
        response = self.client.get('/portal/kiosk-qr/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Берди Мурадов')

    def test_admin_gets_qr_for_selected_employee(self):
        self.client.force_login(self.admin)
        response = self.client.get(f'/portal/kiosk-qr/?user_id={self.user.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<svg', response.content)
        self.assertContains(response, 'Берди Мурадов')

    def test_unknown_user_id_shows_notice(self):
        self.client.force_login(self.admin)
        response = self.client.get('/portal/kiosk-qr/?user_id=999999')
        self.assertNotIn(b'<svg', response.content)
        self.assertContains(response, 'не найден')
