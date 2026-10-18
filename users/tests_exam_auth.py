import json

from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import User


@override_settings(EXAM_SL_AUTH_SERVICE_TOKEN='test-exam-token')
class ExamAuthenticationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='manager@example.com',
            password='StrongPassword123!',
            first_name='Test',
            last_name='Manager',
            role='manager',
        )
        self.url = reverse('exam_authenticate')
        self.headers = {'HTTP_AUTHORIZATION': 'Bearer test-exam-token'}

    def post(self, payload, **headers):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type='application/json',
            secure=True,
            **headers,
        )

    def test_returns_manager_identity(self):
        response = self.post(
            {'username': 'MANAGER@example.com', 'password': 'StrongPassword123!'},
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['email'], 'manager@example.com')
        self.assertEqual(response.json()['display_name'], 'Test Manager')

    def test_rejects_bad_password(self):
        response = self.post(
            {'username': self.user.email, 'password': 'wrong'},
            **self.headers,
        )
        self.assertEqual(response.status_code, 401)

    def test_requires_separate_service_token(self):
        response = self.post(
            {'username': self.user.email, 'password': 'StrongPassword123!'},
        )
        self.assertEqual(response.status_code, 403)
