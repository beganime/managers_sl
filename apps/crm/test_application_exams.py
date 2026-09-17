import base64
import json
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import Company

from .credentials import decrypt_external_secret
from .exam_registry import ExamRegistryError, acknowledge_application_exam, upsert_application_exam
from .models import ActivityLog, Application, ApplicationExam, ApplicationExamEvent, Client


TEST_KEY = base64.urlsafe_b64encode(b'application-exam-test-key-32byte').decode('ascii')


@override_settings(EXTERNAL_ACCOUNT_ENCRYPTION_KEY=TEST_KEY)
class CanonicalApplicationExamTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Exam registry tests')
        self.admin = get_user_model().objects.create_superuser(
            email='exam-admin@example.invalid', password='test-password',
        )
        self.student = Client.objects.create(
            company=self.company, manager=self.admin, full_name='Иван Иванов',
            phone='+00000000020', sl_id='SL-2027-000020',
        )
        self.application = Application.objects.create(
            client=self.student, company=self.company, manager=self.admin,
            university_name='КФУ', program_name='Лечебное дело',
        )
        self.when = timezone.now() + timedelta(days=3)

    def test_exam_is_bound_to_application_encrypted_and_advances_stage(self):
        exam, created = upsert_application_exam(
            application=self.application, subject='Русский язык', scheduled_at=self.when,
            timezone='Europe/Moscow', source_service='exam_sl', source_id='exam-1',
            event_id=uuid4(), secret='private-exam-password', actor=self.admin,
        )
        self.assertTrue(created)
        self.assertEqual(exam.student, self.student)
        self.assertNotIn('private-exam-password', exam.secret_ciphertext)
        self.assertEqual(decrypt_external_secret(exam.secret_ciphertext), 'private-exam-password')
        self.application.refresh_from_db()
        self.assertEqual(self.application.current_stage, Application.STAGE_EXAM_SCHEDULED)
        self.assertTrue(ActivityLog.objects.filter(action='EXAM_CREATED', application=self.application).exists())

    def test_event_is_idempotent_and_source_cannot_move_between_applications(self):
        event_id = uuid4()
        first, created = upsert_application_exam(
            application=self.application, subject='Химия', scheduled_at=self.when,
            source_service='exam_sl', source_id='exam-2', event_id=event_id,
        )
        replay, replay_created = upsert_application_exam(
            application=self.application, subject='Подмена', scheduled_at=self.when + timedelta(days=1),
            source_service='exam_sl', source_id='exam-2', event_id=event_id,
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(replay.pk, first.pk)
        self.assertEqual(ApplicationExamEvent.objects.filter(event_id=event_id).count(), 1)

        other = Application.objects.create(
            client=self.student, company=self.company, manager=self.admin,
            university_name='РУДН', program_name='Стоматология',
        )
        with self.assertRaises(ExamRegistryError):
            upsert_application_exam(
                application=other, subject='Химия', scheduled_at=self.when,
                source_service='exam_sl', source_id='exam-2', event_id=uuid4(),
            )

    def test_acknowledgement_is_idempotent(self):
        exam, _ = upsert_application_exam(
            application=self.application, subject='Биология', scheduled_at=self.when,
            source_service='exam_sl', source_id='exam-3', event_id=uuid4(),
        )
        event_id = uuid4()
        acknowledged, changed = acknowledge_application_exam(
            exam, acknowledged_at=timezone.now(), source_service='students_life', event_id=event_id,
        )
        replay, replay_changed = acknowledge_application_exam(
            exam, acknowledged_at=timezone.now() + timedelta(minutes=1),
            source_service='students_life', event_id=event_id,
        )
        self.assertTrue(changed)
        self.assertFalse(replay_changed)
        self.assertEqual(replay.pk, acknowledged.pk)

    def test_api_does_not_expose_secret(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        response = api.post(reverse('crm-application-exam-list'), {
            'application': self.application.pk,
            'subject': 'Математика',
            'scheduled_at': self.when.isoformat(),
            'timezone': 'Asia/Ashgabat',
            'source_service': 'manager_api',
            'source_id': 'manager-exam-1',
            'secret': 'never-return-this',
            'event_id': str(uuid4()),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['has_secret'])
        self.assertNotIn('secret', response.data)
        exam = ApplicationExam.objects.get()
        self.assertEqual(exam.source_service, 'manager_api')
        self.assertTrue(exam.source_id.startswith('manager-api-'))

        deleted = api.delete(reverse('crm-application-exam-detail', args=[exam.pk]), {'comment': 'Отменён'}, format='json')
        self.assertEqual(deleted.status_code, 204, deleted.data)
        exam.refresh_from_db()
        self.assertEqual(exam.status, ApplicationExam.STATUS_CANCELLED)
        self.assertTrue(exam.events.filter(action='EXAM_UPDATED').exists())

    @override_settings(EXAM_SL_AUTH_SERVICE_TOKEN='exam-service-test-token')
    def test_exam_service_resolves_application_and_replays_event_safely(self):
        event_id = str(uuid4())
        payload = {
            'sl_id': self.student.sl_id,
            'university': 'КФУ',
            'program': 'Лечебное дело',
            'source_id': 'exam-sl-88',
            'event_id': event_id,
            'subject': 'Химия',
            'scheduled_at': self.when.isoformat(),
            'timezone': 'Asia/Ashgabat',
        }
        headers = {'HTTP_AUTHORIZATION': 'Bearer exam-service-test-token'}
        first = self.client.post(reverse('exam_records'), json.dumps(payload), content_type='application/json', **headers)
        replay = self.client.post(reverse('exam_records'), json.dumps(payload), content_type='application/json', **headers)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(first.json()['public_id'], replay.json()['public_id'])
        self.assertEqual(ApplicationExam.objects.count(), 1)

        context = self.client.get(reverse('exam_records'), {'q': self.student.sl_id}, **headers)
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.json()['results'][0]['application_public_id'], str(self.application.public_id))

        forbidden = self.client.post(reverse('exam_records'), json.dumps(payload), content_type='application/json')
        self.assertEqual(forbidden.status_code, 403)

    @override_settings(LEADS_API_KEY='mobile-service-test-key')
    def test_client_seen_callback_updates_canonical_exam_idempotently(self):
        exam, _ = upsert_application_exam(
            application=self.application, subject='Физика', scheduled_at=self.when,
            source_service='exam_sl', source_id='exam-seen-1', event_id=uuid4(),
        )
        body = {'acknowledged_at': timezone.now().isoformat()}
        headers = {'HTTP_X_API_KEY': 'mobile-service-test-key'}
        first = self.client.post(
            reverse('exam_seen', args=[str(exam.public_id)]), json.dumps(body),
            content_type='application/json', **headers,
        )
        replay = self.client.post(
            reverse('exam_seen', args=[str(exam.public_id)]), json.dumps(body),
            content_type='application/json', **headers,
        )
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(replay.status_code, 200, replay.content)
        exam.refresh_from_db()
        self.assertIsNotNone(exam.client_acknowledged_at)
        self.assertEqual(exam.events.filter(action='EXAM_ACKNOWLEDGED').count(), 1)
