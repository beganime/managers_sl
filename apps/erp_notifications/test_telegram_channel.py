from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.attendance.models import EmployeeTelegramAccount
from apps.organizations.models import Company

from .models import Notification, NotificationTemplate
from .services import create_notification, send_notification


def transport_mock():
    post_mock = MagicMock()

    def side_effect(method_url=None, payload=None, **kwargs):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {'ok': True}
        return response

    post_mock.side_effect = side_effect
    return patch('requests.post', side_effect=side_effect)


@override_settings(
    ATTENDANCE_TELEGRAM_ENABLED=True,
    ATTENDANCE_TELEGRAM_BOT_TOKEN='token',
)
class TelegramChannelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='SL', country='Туркменистан')
        self.user = get_user_model().objects.create_user(email='ntf-user@example.com', password='pw')

    def _notification(self, channel=NotificationTemplate.CHANNEL_TELEGRAM):
        return create_notification(
            self.user,
            title='Тестовое уведомление',
            body='Текст тестового уведомления.',
            channel=channel,
            company=self.company,
            queue=False,
        )

    def test_telegram_delivered_to_linked_account(self):
        EmployeeTelegramAccount.objects.create(employee=self.user, telegram_user_id=201, chat_id=8001)
        notification = self._notification()
        with transport_mock() as post_mock:
            sent = send_notification(notification)
        self.assertTrue(sent)
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.STATUS_SENT)
        sent_calls = [c for c in post_mock.call_args_list if 'sendMessage' in c[0][0]]
        self.assertEqual(len(sent_calls), 1)
        self.assertIn('Тестовое уведомление', sent_calls[0][1]['json']['text'])
        self.assertEqual(sent_calls[0][1]['json']['chat_id'], 8001)

    def test_telegram_without_account_falls_back_to_in_app(self):
        notification = self._notification()
        with transport_mock() as post_mock:
            sent = send_notification(notification)
        self.assertTrue(sent)
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.STATUS_SENT)
        self.assertEqual(post_mock.call_count, 0)

    def test_in_app_channel_still_works(self):
        notification = self._notification(channel=NotificationTemplate.CHANNEL_IN_APP)
        sent = send_notification(notification)
        self.assertTrue(sent)
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.STATUS_SENT)

    def test_cancelled_notification_not_sent(self):
        notification = self._notification()
        notification.status = Notification.STATUS_CANCELLED
        notification.save(update_fields=['status'])
        self.assertFalse(send_notification(notification))
