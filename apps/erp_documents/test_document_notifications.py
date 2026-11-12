from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.attendance.models import EmployeeTelegramAccount
from apps.erp_notifications.models import Notification
from apps.organizations.models import Company, Office
from apps.payments.models import PaymentRecipient

from .models import DocumentTemplate, GeneratedDocument
from .tasks import notify_document_admins


@override_settings(
    ATTENDANCE_TELEGRAM_ENABLED=True,
    ATTENDANCE_TELEGRAM_BOT_TOKEN='token',
)
class DocumentNotificationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='SL', country='Туркменистан')
        self.office = Office.objects.create(company=self.company, name='Ашхабад')
        self.manager = get_user_model().objects.create_user(email='doc-mgr@example.com', password='pw', first_name='Дина')
        self.admin = get_user_model().objects.create_user(email='doc-adm@example.com', password='pw', role='admin')
        PaymentRecipient.objects.create(user=self.admin)
        self.template = DocumentTemplate.objects.create(
            name='Договор обучения',
            code='contract',
            file=SimpleUploadedFile('contract.docx', b'fake-docx'),
        )
        self.document = GeneratedDocument.objects.create(
            company=self.company,
            office=self.office,
            template=self.template,
            manager=self.manager,
            title='Договор №1',
        )

    def transport(self):
        post_mock = MagicMock()

        def side_effect(method_url=None, payload=None, **kwargs):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {'ok': True}
            return response

        post_mock.side_effect = side_effect
        return patch('requests.post', side_effect=side_effect)

    def test_task_notifies_linked_admin_and_creates_in_app(self):
        EmployeeTelegramAccount.objects.create(employee=self.admin, telegram_user_id=301, chat_id=9001)
        with self.transport() as post_mock:
            result = notify_document_admins.run(self.document.pk)
        self.assertEqual(result['sent'], 1)
        sent_calls = [c for c in post_mock.call_args_list if 'sendMessage' in c[0][0]]
        self.assertEqual(len(sent_calls), 1)
        self.assertIn('Договор обучения', sent_calls[0][1]['json']['text'])
        self.assertIn('/portal/documents/', sent_calls[0][1]['json']['text'])
        self.assertTrue(Notification.objects.filter(recipient=self.admin, title='Новый документ').exists())

    def test_task_retries_without_linked_recipients(self):
        try:
            notify_document_admins.run(self.document.pk)
        except Exception as exc:
            self.assertIn('Retry', type(exc).__name__)
        else:
            self.fail('Ожидался retry')

    def test_signal_enqueues_notification_on_create(self):
        from apps.erp_documents import signals

        with patch.object(signals, '_safe_delay') as delay_mock:
            with self.captureOnCommitCallbacks(execute=True):
                GeneratedDocument.objects.create(
                    company=self.company,
                    template=self.template,
                    manager=self.manager,
                    title='Договор №2',
                )
        self.assertEqual(delay_mock.call_count, 1)

    def test_signal_not_fired_for_error_documents(self):
        from apps.erp_documents import signals

        with patch.object(signals, '_safe_delay') as delay_mock:
            with self.captureOnCommitCallbacks(execute=True):
                doc = GeneratedDocument.objects.create(
                    company=self.company,
                    template=self.template,
                    manager=self.manager,
                    title='Договор №3',
                )
                doc.status = GeneratedDocument.STATUS_ERROR
                doc.save(update_fields=['status'])
        # create: 1 вызов; update: сигнал создания не повторяется
        self.assertEqual(delay_mock.call_count, 1)
