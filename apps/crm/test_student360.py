from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.education.models import Country, Program, University
from apps.organizations.models import Company

from .models import Application, Client, ClientActivity, ClientNote


class Student360Tests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Student 360 test')
        self.admin = get_user_model().objects.create_user(
            email='student-360-admin@example.invalid', password='test-only-password', is_staff=True,
        )
        self.other = get_user_model().objects.create_user(
            email='student-360-outsider@example.invalid', password='test-only-password',
        )
        self.shared = get_user_model().objects.create_user(
            email='student-360-shared@example.invalid', password='test-only-password', role='employee',
        )
        self.student = Client.objects.create(
            company=self.company, manager=self.admin, full_name='Тестовый Студент',
            phone='+99360000000', sl_id='SL-001', passport_inter_num='TEST-PASSPORT',
        )
        country = Country.objects.create(name='Тестовая страна')
        university = University.objects.create(
            name='Тестовый университет', abbreviation='ТУ', country=country,
        )
        program = Program.objects.create(name='Тестовая программа', university=university)
        self.application = Application.objects.create(
            client=self.student, company=self.company, manager=self.admin,
            university=university, program=program, country_reference=country,
        )
        ClientActivity.objects.create(
            client=self.student, manager=self.admin, title='Проверка карточки',
        )
        ClientNote.objects.create(
            client=self.student, author=self.admin, text='Приватная тестовая заметка', is_private=True,
        )
        self.student.shared_with.add(self.shared)
        self.api = APIClient()

    def test_requires_authentication(self):
        response = self.api.get(reverse('student-360', args=[self.student.public_id]))
        self.assertEqual(response.status_code, 401)

    def test_uuid_snapshot_uses_canonical_catalog_and_contains_timeline(self):
        self.api.force_authenticate(self.admin)
        response = self.api.get(reverse('student-360', args=[self.student.public_id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['student']['public_id'], str(self.student.public_id))
        self.assertEqual(response.data['applications'][0]['public_id'], str(self.application.public_id))
        self.assertEqual(response.data['applications'][0]['university'], 'ТУ')
        self.assertEqual(response.data['applications'][0]['program'], 'Тестовая программа')
        self.assertEqual(response.data['student']['passport_inter_num'], 'TEST-PASSPORT')
        self.assertTrue(any(row['kind'] == 'activity' for row in response.data['timeline']))

    def test_out_of_scope_student_is_not_disclosed(self):
        self.api.force_authenticate(self.other)
        response = self.api.get(reverse('student-360', args=[self.student.public_id]))
        self.assertEqual(response.status_code, 404)

    def test_shared_user_can_read_basic_card_but_not_sensitive_fields(self):
        self.api.force_authenticate(self.shared)
        response = self.api.get(reverse('student-360', args=[self.student.public_id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('passport_inter_num', response.data['student'])
        self.assertEqual(response.data['documents'], [])
        self.assertEqual(response.data['generated_documents'], [])
        self.assertEqual(response.data['contracts'], [])

    def test_legacy_primary_key_action_remains_available(self):
        self.api.force_authenticate(self.admin)
        response = self.api.get(reverse('crm-client-student-360', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['student']['sl_id'], 'SL-001')
