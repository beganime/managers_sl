from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.core.permissions import get_employee_profile
from apps.crm.models import Client
from apps.employees.models import EmployeeProfile, EmployeeRole
from apps.organizations.models import Company, Office

from .models import Payment, PaymentRecipient


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.office = Office.objects.create(company=self.company, name='Ашхабад')
        self.role = EmployeeRole.objects.create(code='manager', name='Менеджер', role_type='manager')
        self.manager = get_user_model().objects.create_user(email='pay-manager@example.com', password='pw', first_name='Пётр')
        EmployeeProfile.objects.create(user=self.manager, company=self.company, office=self.office, role=self.role)
        self.admin = get_user_model().objects.create_user(email='pay-admin@example.com', password='pw', role='admin')
        self.client_obj = Client.objects.create(company=self.company, office=self.office, manager=self.manager, full_name='Иван Тестов', phone='123')

    def photo(self):
        return SimpleUploadedFile('check.jpg', b'\xff\xd8\xff\xe0fake-jpeg', content_type='image/jpeg')

    def test_manager_creates_payment_and_page_renders(self):
        self.client.force_login(self.manager)
        with patch('apps.payments.views.queue_payment_admins_notification') as notify:
            response = self.client.post(reverse('portal:payments'), {
                'payment-client': str(self.client_obj.pk),
                'payment-amount': '1500.50',
                'payment-photo': self.photo(),
                'payment-note': 'Чек из банка',
            })
        self.assertEqual(response.status_code, 302)
        payment = Payment.objects.get()
        self.assertEqual(payment.manager, self.manager)
        self.assertEqual(payment.amount, Decimal('1500.50'))
        self.assertEqual(payment.status, Payment.STATUS_PENDING)
        notify.assert_called_once()
        page = self.client.get(reverse('portal:payments'))
        self.assertContains(page, 'Иван Тестов')
        self.assertContains(page, 'На проверке')

    def test_manager_cannot_open_admin_page(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('portal:payments_admin'))
        self.assertEqual(response.status_code, 403)

    def test_admin_without_profile_redirected_to_admin_page(self):
        # Администратор без профиля сотрудника получает страницу проверки оплат,
        # а не 403 на странице подачи оплат.
        self.assertIsNone(get_employee_profile(self.admin))
        self.client.force_login(self.admin)
        response = self.client.get(reverse('portal:payments'))
        self.assertRedirects(response, reverse('portal:payments_admin'))
        page = self.client.get(reverse('portal:payments_admin'))
        self.assertEqual(page.status_code, 200)

    def test_admin_confirms_and_totals_update(self):
        Payment.objects.create(manager=self.manager, client=self.client_obj, amount=Decimal('700'), photo=self.photo())
        self.client.force_login(self.admin)
        payment = Payment.objects.get()
        response = self.client.post(reverse('portal:payments_admin'), {'payment_id': payment.pk, 'action': 'confirm'}, follow=True)
        self.assertContains(response, 'подтверждена')
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_CONFIRMED)
        self.assertEqual(payment.reviewed_by, self.admin)
        page = self.client.get(reverse('portal:payments_admin'))
        self.assertContains(page, '700')

    def test_reject_keeps_out_of_totals(self):
        Payment.objects.create(manager=self.manager, client=self.client_obj, amount=Decimal('700'), photo=self.photo())
        self.client.force_login(self.admin)
        self.client.post(reverse('portal:payments_admin'), {'payment_id': Payment.objects.get().pk, 'action': 'reject'})
        page = self.client.get(reverse('portal:payments_admin'))
        self.assertNotContains(page, '<strong>700</strong>')

    def test_recipients_selection(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('portal:payments_admin'), {'action': 'recipients', 'recipient': [str(self.admin.pk)]})
        self.assertTrue(PaymentRecipient.objects.filter(user=self.admin).exists())
        self.client.post(reverse('portal:payments_admin'), {'action': 'recipients', 'recipient': []})
        self.assertFalse(PaymentRecipient.objects.exists())


class PaymentNotificationTaskTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.office = Office.objects.create(company=self.company, name='Ашхабад')
        self.role = EmployeeRole.objects.create(code='manager', name='Менеджер', role_type='manager')
        self.manager = get_user_model().objects.create_user(email='n-manager@example.com', password='pw')
        EmployeeProfile.objects.create(user=self.manager, company=self.company, office=self.office, role=self.role)
        self.admin = get_user_model().objects.create_user(email='n-admin@example.com', password='pw')
        self.client_obj = Client.objects.create(company=self.company, office=self.office, manager=self.manager, full_name='Клиент К', phone='1')
        PaymentRecipient.objects.create(user=self.admin)

    def photo(self):
        return SimpleUploadedFile('c.jpg', b'x', content_type='image/jpeg')

    @patch('apps.attendance.telegram.send_telegram_message')
    def test_task_notifies_linked_recipients(self, send_mock):
        from apps.attendance.models import EmployeeTelegramAccount
        from .tasks import notify_payment_admins

        send_mock.return_value = (True, '')
        EmployeeTelegramAccount.objects.create(employee=self.admin, telegram_user_id=101, chat_id=5001)
        EmployeeTelegramAccount.objects.create(employee=self.manager, telegram_user_id=102, chat_id=5002)
        payment = Payment.objects.create(manager=self.manager, client=self.client_obj, amount=Decimal('99'), photo=self.photo())
        result = notify_payment_admins.run(payment.pk)
        self.assertEqual(result['sent'], 1)
        self.assertEqual(send_mock.call_count, 1)
        msg, chat_id = send_mock.call_args[0]
        self.assertIn('Новая оплата', msg)
        self.assertEqual(chat_id, 5001)

    @patch('apps.attendance.telegram.send_telegram_message')
    def test_task_retries_when_no_recipients_linked(self, send_mock):
        from .tasks import notify_payment_admins
        payment = Payment.objects.create(manager=self.manager, client=self.client_obj, amount=Decimal('99'), photo=self.photo())
        try:
            notify_payment_admins.run(payment.pk)
        except Exception as exc:
            self.assertIn('Retry', type(exc).__name__)
        else:
            self.fail('Ожидался retry')
