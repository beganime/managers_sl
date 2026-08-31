from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.crm.models import Client
from apps.organizations.models import Company


class ClientExamAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='manager.exam@example.com',
            password='test-password',
        )
        self.other_user = get_user_model().objects.create_user(
            email='other.exam@example.com',
            password='test-password',
        )
        self.company = Company.objects.create(name='Students Life Test')
        self.client_record = Client.objects.create(
            company=self.company,
            manager=self.user,
            full_name='Тестовый Клиент',
            phone='+99360000000',
            mobile_app_user_id=77,
        )
        self.client.force_authenticate(self.user)
        self.url = f'/api/app/clients/{self.client_record.pk}/exams/'

    @patch('apps.portal.views.students_life_api_request')
    def test_lists_client_exams_through_server_proxy(self, request_mock):
        request_mock.return_value = (True, [{'id': 5, 'university': 'КФУ'}])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['client']['mobile_app_user_id'], 77)
        self.assertEqual(response.data['exams'][0]['id'], 5)
        request_mock.assert_called_once_with(
            'notifications/clients/77/exams/', payload=None, method='GET'
        )

    @patch('apps.portal.views.students_life_api_request')
    def test_creates_exam_and_keeps_service_key_on_backend(self, request_mock):
        request_mock.return_value = (True, {'id': 9, 'sync_status': 'created'})

        response = self.client.post(
            self.url,
            {
                'subject': 'Вступительный экзамен',
                'university': 'КФУ',
                'exam_date': '2027-06-10',
                'exam_time': '10:30',
                'comment': 'Прибыть заранее',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['exam']['id'], 9)
        sent_payload = request_mock.call_args.kwargs['payload']
        self.assertEqual(sent_payload['university'], 'КФУ')
        self.assertEqual(sent_payload['timezone'], 'Asia/Ashgabat')

    def test_hides_another_managers_client(self):
        other_client = Client.objects.create(
            company=self.company,
            manager=self.other_user,
            full_name='Чужой Клиент',
            phone='+99361111111',
            mobile_app_user_id=78,
        )

        response = self.client.get(f'/api/app/clients/{other_client.pk}/exams/')

        self.assertEqual(response.status_code, 404)

    def test_requires_complete_exam_schedule(self):
        response = self.client.post(
            self.url,
            {'subject': 'Экзамен', 'university': 'КФУ'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
