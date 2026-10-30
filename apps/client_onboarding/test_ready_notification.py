from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, override_settings
from .tasks import notify_onboarding_status


@override_settings(STUDENTS_LIFE_PROVISION_API_URL='https://example.invalid/provision/', STUDENTS_LIFE_PROVISION_TOKEN='test-only')
class AccountReadyNotificationTests(SimpleTestCase):
    def submission(self, ready):
        steps = Mock()
        steps.filter.return_value.exists.return_value = ready
        return SimpleNamespace(status='approved', client_id=1,
            client=SimpleNamespace(sl_id='SL-TEST', custom_data={'mobile_password': 'never-in-push'}),
            provisioning_steps=steps, public_id='test-public-id')

    @patch('apps.client_onboarding.tasks.post_service')
    @patch('apps.client_onboarding.tasks.OnboardingSubmission.objects')
    def test_no_ready_message_before_account_exists(self, objects, post):
        objects.select_related.return_value.get.return_value = self.submission(False)
        self.assertEqual(notify_onboarding_status.run(1)['reason'], 'account_not_ready')
        post.assert_not_called()

    @patch('apps.client_onboarding.tasks.post_service', return_value={'status': 'sent'})
    @patch('apps.client_onboarding.tasks.OnboardingSubmission.objects')
    def test_ready_message_never_contains_credentials(self, objects, post):
        objects.select_related.return_value.get.return_value = self.submission(True)
        notify_onboarding_status.run(1)
        payload = post.call_args.args[2]
        self.assertEqual(payload['title'], 'Личный кабинет готов')
        self.assertNotIn('never-in-push', payload['body'])
        self.assertIn('экспресс-заявку', payload['body'])
