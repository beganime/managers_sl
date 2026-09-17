import base64
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Company

from .credentials import decrypt_external_secret, encrypt_external_secret
from .models import ActivityLog, Application, Client, ExternalAccount


TEST_KEY = base64.urlsafe_b64encode(b'external-account-test-key-32byte').decode('ascii')


@override_settings(EXTERNAL_ACCOUNT_ENCRYPTION_KEY=TEST_KEY)
class ExternalAccountTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='External account tests')
        self.admin = get_user_model().objects.create_superuser(
            email='external-admin@example.invalid', password='test-only-password',
        )
        self.staff = get_user_model().objects.create_user(
            email='external-staff@example.invalid', password='test-only-password', is_staff=True,
        )
        self.student = Client.objects.create(
            company=self.company, manager=self.admin, full_name='External Account Student',
            phone='+00000000010', sl_id='SL-001',
        )
        self.application = Application.objects.create(
            client=self.student, company=self.company, manager=self.admin,
            university_name='Test University', program_name='Medicine',
        )
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def create_account(self, *, secret='private-password', event_id=None):
        response = self.api.post(
            reverse('crm-external-account-list'),
            {
                'student': self.student.pk,
                'application': self.application.pk,
                'system': ExternalAccount.SYSTEM_UNIVERSITY,
                'provider_name': 'Test University portal',
                'portal_url': 'https://university.example.invalid/login',
                'email': 'student@example.invalid',
                'login': 'SL001',
                'secret': secret,
                'status': ExternalAccount.STATUS_CREATED,
                'responsible': self.admin.pk,
                'event_id': str(event_id or uuid4()),
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response, ExternalAccount.objects.get()

    def test_secret_is_authenticated_encrypted_and_not_returned_by_regular_api(self):
        encrypted = encrypt_external_secret('private-password')
        self.assertNotIn('private-password', encrypted)
        self.assertEqual(decrypt_external_secret(encrypted), 'private-password')

        response, account = self.create_account()

        self.assertNotIn('secret', response.data)
        self.assertTrue(response.data['has_secret'])
        self.assertNotIn('private-password', account.secret_ciphertext)
        self.assertEqual(ActivityLog.objects.get().action, 'EXTERNAL_ACCOUNT_CREATED')
        self.assertNotIn('private-password', str(ActivityLog.objects.get().new_data))

    def test_only_explicit_secret_permission_can_reveal_password(self):
        _response, account = self.create_account()
        reveal_url = reverse('crm-external-account-reveal-secret', args=[account.pk])

        allowed = self.api.post(reveal_url, format='json')
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data['secret'], 'private-password')
        self.assertEqual(allowed['Cache-Control'], 'no-store')
        viewed = ActivityLog.objects.get(action='EXTERNAL_ACCOUNT_SECRET_VIEWED')
        self.assertEqual(viewed.actor, self.admin)
        self.assertNotIn('private-password', str(viewed.metadata))

        self.api.force_authenticate(self.staff)
        denied = self.api.post(reveal_url, format='json')
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(ActivityLog.objects.filter(action='EXTERNAL_ACCOUNT_SECRET_VIEWED').count(), 1)

    def test_application_must_belong_to_student(self):
        other = Client.objects.create(
            company=self.company, manager=self.admin, full_name='Other Student', phone='+00000000011',
        )
        response = self.api.post(
            reverse('crm-external-account-list'),
            {
                'student': other.pk,
                'application': self.application.pk,
                'system': ExternalAccount.SYSTEM_RUID,
                'provider_name': 'RUID',
                'responsible': self.admin.pk,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ExternalAccount.objects.count(), 0)

    def test_delete_archives_instead_of_erasing_account(self):
        _response, account = self.create_account(secret='')
        response = self.api.delete(reverse('crm-external-account-detail', args=[account.pk]))

        self.assertEqual(response.status_code, 204)
        account.refresh_from_db()
        self.assertEqual(account.status, ExternalAccount.STATUS_ARCHIVED)
        self.assertEqual(ActivityLog.objects.filter(action='EXTERNAL_ACCOUNT_UPDATED').count(), 1)

    def test_student360_contains_metadata_but_never_secret(self):
        self.create_account()
        response = self.api.get(reverse('student-360', args=[self.student.public_id]))

        self.assertEqual(response.status_code, 200)
        account = response.data['external_accounts'][0]
        self.assertTrue(account['has_secret'])
        self.assertNotIn('secret', account)
        self.assertTrue(response.data['capabilities']['external_accounts_registry'])
