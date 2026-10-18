import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import User


@override_settings(DISK_AUTH_SERVICE_TOKEN='test-disk-token')
class DiskAuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='manager@example.com',
            password='StrongPassword123!',
            first_name='Test',
            last_name='Manager',
            role='manager',
        )
        self.url = reverse('disk_authenticate')
        self.headers = {'HTTP_AUTHORIZATION': 'Bearer test-disk-token'}

    def post(self, payload, **headers):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            secure=True,
            **headers,
        )

    def test_accepts_active_manager(self):
        response = self.post(
            {'username': self.user.email, 'password': 'StrongPassword123!'},
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['username'], self.user.email)
        self.assertTrue(response.json()['authenticated'])

    def test_rejects_invalid_password(self):
        response = self.post(
            {'username': self.user.email, 'password': 'wrong'},
            **self.headers,
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()['authenticated'])

    def test_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])

        response = self.post(
            {'username': self.user.email, 'password': 'StrongPassword123!'},
            **self.headers,
        )

        self.assertEqual(response.status_code, 401)

    @mock.patch('users.disk_auth.authenticate')
    def test_rejects_fired_employee(self, mocked_authenticate):
        employee = mock.Mock(is_active=True, work_status='fired', role_id=1)
        user = mock.Mock(
            is_active=True,
            is_superuser=False,
            is_staff=False,
            role='viewer',
            employee_profile=employee,
        )
        mocked_authenticate.return_value = user

        response = self.post(
            {'username': 'viewer@example.com', 'password': 'password'},
            **self.headers,
        )

        self.assertEqual(response.status_code, 401)

    @mock.patch('users.disk_auth.authenticate')
    def test_rejects_accountant_with_employee_profile(self, mocked_authenticate):
        employee_role = mock.Mock(role_type='accountant')
        employee = mock.Mock(
            is_active=True,
            work_status='working',
            role_id=1,
            role=employee_role,
        )
        user = mock.Mock(
            is_active=True,
            is_authenticated=True,
            is_superuser=False,
            role='manager',
            employee_profile=employee,
        )
        mocked_authenticate.return_value = user

        response = self.post(
            {'username': 'accountant@example.com', 'password': 'password'},
            **self.headers,
        )

        self.assertEqual(response.status_code, 401)

    def test_requires_service_token(self):
        response = self.post(
            {'username': self.user.email, 'password': 'StrongPassword123!'},
        )

        self.assertEqual(response.status_code, 403)
