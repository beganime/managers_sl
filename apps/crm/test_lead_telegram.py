import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.attendance.models import EmployeeTelegramAccount
from apps.crm.models import Lead
from apps.organizations.models import Company, Office

from .lead_telegram import notify_new_lead_buttons

WEBHOOK_SECRET = 'test-secret'


def transport_factory():
    """Один мок на весь requests.post: маршрутизация по URL."""
    post_mock = MagicMock()

    def side_effect(method_url=None, payload=None, **kwargs):
        response = MagicMock()
        if '/bot' in str(method_url):
            response.status_code = 200
            response.json.return_value = {'ok': True}
        else:
            response.status_code = 201
            response.json.return_value = {'id': 7}
        return response

    post_mock.side_effect = side_effect
    return post_mock


def patch_transport():
    """Патчит глобальный requests.post (модуль общий для всех приложений)."""
    return patch('requests.post', side_effect=transport_factory().side_effect)


@override_settings(
    ATTENDANCE_TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET,
    ATTENDANCE_TELEGRAM_BOT_TOKEN='token',
    ATTENDANCE_TELEGRAM_CHAT_ID='-100',
    ATTENDANCE_TELEGRAM_API_BASE='https://api.telegram.org',
)
class LeadTelegramTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='SL', country='Туркменистан')
        self.office = Office.objects.create(company=self.company, name='Ашхабад')
        self.manager = get_user_model().objects.create_user(email='lead-mgr@example.com', password='pw', first_name='Мария')
        self.admin = get_user_model().objects.create_user(email='lead-adm@example.com', password='pw', role='admin')
        self.lead = Lead.objects.create(company=self.company, office=self.office, full_name='Лид Тестов', phone='555', comment='Хочет поступать')

    def post_callback(self, data, telegram_user_id=101):
        payload = {
            'callback_query': {
                'id': 'cbq1',
                'from': {'id': telegram_user_id},
                'data': data,
                'message': {'chat': {'id': -100}, 'message_id': 50},
            },
        }
        return self.client.post(
            reverse('attendance_telegram_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
        )

    def test_new_lead_notification_has_buttons(self):
        with patch_transport() as post_mock:
            result = notify_new_lead_buttons.run(self.lead.pk)
        self.assertTrue(result['sent'])
        payload = post_mock.call_args[1]['json']
        self.assertIn('inline_keyboard', payload['reply_markup'])
        keyboard_data = str(payload['reply_markup'])
        self.assertIn(f'sl:ld:{self.lead.pk}:take', keyboard_data)
        self.assertIn('Лид Тестов', payload['text'])

    def test_unlinked_user_gets_denied(self):
        with patch_transport() as post_mock:
            response = self.post_callback(f'sl:ld:{self.lead.pk}:take', telegram_user_id=999)
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.manager_id)
        answered = [c for c in post_mock.call_args_list if 'answerCallbackQuery' in c[0][0]]
        self.assertEqual(len(answered), 1)

    def test_manager_takes_lead_and_pushed_to_elite_task(self):
        EmployeeTelegramAccount.objects.create(employee=self.manager, telegram_user_id=101, chat_id=7001)
        with patch_transport() as post_mock, \
             override_settings(ELITE_TASK_INTEGRATION_KEY='key'), \
             patch('apps.crm.lead_telegram.enqueue_lead_to_elite_task') as push:
            response = self.post_callback(f'sl:ld:{self.lead.pk}:take')
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.manager_id, self.manager.id)
        self.assertEqual(self.lead.status, 'contacted')
        push.assert_called_once_with(self.lead.pk)
        answered = [c for c in post_mock.call_args_list if 'answerCallbackQuery' in c[0][0]]
        self.assertEqual(len(answered), 1)
        self.assertIn('Elite Task', answered[0][1]['json']['text'])
        edited = [c for c in post_mock.call_args_list if 'editMessageText' in c[0][0]]
        self.assertEqual(len(edited), 1)

    def test_second_manager_cannot_take_taken_lead(self):
        EmployeeTelegramAccount.objects.create(employee=self.manager, telegram_user_id=101, chat_id=7001)
        other = get_user_model().objects.create_user(email='lead-other@example.com', password='pw')
        self.lead.take_responsibility(other)
        with patch_transport() as post_mock:
            self.post_callback(f'sl:ld:{self.lead.pk}:take')
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.manager_id, other.id)
        answered = [c for c in post_mock.call_args_list if 'answerCallbackQuery' in c[0][0]]
        self.assertEqual(len(answered), 1)
        self.assertIn('уже в работе', answered[0][1]['json']['text'])

    def test_done_archives_free_lead(self):
        EmployeeTelegramAccount.objects.create(employee=self.manager, telegram_user_id=101, chat_id=7001)
        self.lead.take_responsibility(self.manager)
        with patch_transport():
            self.post_callback(f'sl:ld:{self.lead.pk}:done')
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.is_archived)

    def test_done_forbidden_for_other_manager(self):
        EmployeeTelegramAccount.objects.create(employee=self.manager, telegram_user_id=101, chat_id=7001)
        other = get_user_model().objects.create_user(email='lead-other2@example.com', password='pw')
        self.lead.take_responsibility(other)
        with patch_transport():
            self.post_callback(f'sl:ld:{self.lead.pk}:done')
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.is_archived)

    def test_unknown_callback_ignored(self):
        with patch_transport() as post_mock:
            response = self.post_callback('something:else')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(post_mock.call_count, 0)

    def test_webhook_requires_secret(self):
        response = self.client.post(
            reverse('attendance_telegram_webhook'),
            data='{}',
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='wrong',
        )
        self.assertEqual(response.status_code, 403)


@override_settings(
    ATTENDANCE_TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET,
    ATTENDANCE_TELEGRAM_BOT_TOKEN='token',
    ATTENDANCE_TELEGRAM_CHAT_ID='-100',
    ATTENDANCE_TELEGRAM_API_BASE='https://api.telegram.org',
)
class SubmissionTelegramTests(TestCase):
    def setUp(self):
        from apps.client_onboarding.models import OnboardingSubmission

        self.manager = get_user_model().objects.create_user(email='sub-mgr@example.com', password='pw', first_name='Олег')
        _, token_hash = OnboardingSubmission.issue_access_token()
        self.submission = OnboardingSubmission.objects.create(
            access_token_hash=token_hash,
            kind=OnboardingSubmission.KIND_APPLICANT,
            stage=OnboardingSubmission.STAGE_EXPRESS,
            academic_year=2027,
            full_name='Анкета Анкетовна',
            phone='777',
        )

    def post_callback(self, data, telegram_user_id=101):
        payload = {
            'callback_query': {
                'id': 'cbq1',
                'from': {'id': telegram_user_id},
                'data': data,
                'message': {'chat': {'id': -100}, 'message_id': 60},
            },
        }
        return self.client.post(
            reverse('attendance_telegram_webhook'),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
        )

    def test_manager_takes_submission(self):
        from apps.client_onboarding.models import OnboardingSubmission

        EmployeeTelegramAccount.objects.create(employee=self.manager, telegram_user_id=101, chat_id=7001)
        with patch_transport() as post_mock:
            response = self.post_callback(f'sl:sub:{self.submission.pk}:take')
        self.assertEqual(response.status_code, 200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, OnboardingSubmission.STATUS_IN_REVIEW)
        self.assertEqual(self.submission.reviewed_by_id, self.manager.id)
        answered = [c for c in post_mock.call_args_list if 'answerCallbackQuery' in c[0][0]]
        self.assertEqual(len(answered), 1)
        self.assertIn('Вы взяли заявку', answered[0][1]['json']['text'])

    def test_done_marks_processed(self):
        from apps.client_onboarding.models import OnboardingSubmission

        EmployeeTelegramAccount.objects.create(employee=self.manager, telegram_user_id=101, chat_id=7001)
        self.submission.status = OnboardingSubmission.STATUS_IN_REVIEW
        self.submission.reviewed_by = self.manager
        self.submission.save(update_fields=['status', 'reviewed_by'])
        with patch_transport():
            self.post_callback(f'sl:sub:{self.submission.pk}:done')
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, OnboardingSubmission.STATUS_PROCESSED)
        self.assertEqual(self.submission.reviewed_by_id, self.manager.id)
