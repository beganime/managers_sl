from unittest.mock import patch, Mock
from django.test import SimpleTestCase
from apps.erp_notifications.push import send_push_to_token


class PreAccountExpoTests(SimpleTestCase):
    @patch('requests.post')
    @patch('apps.erp_notifications.push.init_firebase')
    def test_expo_accepted_without_firebase(self, firebase, post):
        post.return_value = Mock(json=lambda: {'data': {'status': 'ok', 'id': 'test-ticket'}})
        self.assertTrue(send_push_to_token('ExpoPushToken[test]', 'Title', 'Body'))
        firebase.assert_not_called()

    @patch('requests.post')
    def test_expo_rejection_can_be_retried_by_task(self, post):
        post.return_value = Mock(json=lambda: {'data': {'status': 'error'}})
        with self.assertRaises(RuntimeError):
            send_push_to_token('ExpoPushToken[test]', 'Title')
