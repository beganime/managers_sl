from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.employees.models import EmployeeProfile, EmployeeRole
from apps.organizations.models import Company, Office


@override_settings(EMPLOYEE_DIRECTORY_SERVICE_TOKEN='directory-test-token')
class EmployeeDirectoryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life')
        self.office = Office.objects.create(company=self.company, name='Main', city='Ashgabat')
        self.role = EmployeeRole.objects.create(code='manager', name='Manager', role_type='manager')
        self.user = get_user_model().objects.create_user(
            email='employee@example.com',
            password='not-returned',
            first_name='Aman',
            last_name='Amanov',
            middle_name='M.',
        )
        self.profile = EmployeeProfile.objects.create(
            user=self.user,
            company=self.company,
            office=self.office,
            role=self.role,
        )
        self.headers = {'HTTP_AUTHORIZATION': 'Bearer directory-test-token'}

    def test_requires_service_token(self):
        response = self.client.get(reverse('employee_directory'))
        self.assertEqual(response.status_code, 401)

    def test_returns_safe_employee_contract(self):
        response = self.client.get(reverse('employee_directory'), **self.headers)
        self.assertEqual(response.status_code, 200)
        result = response.json()['results'][0]
        self.assertEqual(result['user_id'], self.user.pk)
        self.assertEqual(result['email'], 'employee@example.com')
        self.assertEqual(result['office']['city'], 'Ashgabat')
        self.assertEqual(result['role']['type'], 'manager')
        self.assertNotIn('password', result)
        self.assertNotIn('salary', result)
        self.assertNotIn('notes', result)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_detail_uses_stable_user_id(self):
        response = self.client.get(
            reverse('employee_directory_detail', kwargs={'user_id': self.user.pk}),
            **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['employee']['id'], self.profile.pk)

    def test_active_filter_hides_inactive_employee(self):
        self.profile.work_status = 'fired'
        self.profile.save(update_fields=['work_status', 'updated_at'])
        active = self.client.get(reverse('employee_directory'), **self.headers).json()
        all_records = self.client.get(reverse('employee_directory') + '?status=all', **self.headers).json()
        self.assertEqual(active['results'], [])
        self.assertEqual(len(all_records['results']), 1)

    def test_rejects_invalid_filter(self):
        response = self.client.get(reverse('employee_directory') + '?limit=nope', **self.headers)
        self.assertEqual(response.status_code, 400)
