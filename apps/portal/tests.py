from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.client_onboarding.models import ClientProvisioningStep, OnboardingReviewEvent, OnboardingSubmission
from apps.client_onboarding.services import review_submission
from apps.crm.models import Client
from apps.erp_notifications.models import Notification
from apps.organizations.models import Company
from apps.portal.views import build_client_disk_url


class ClientDiskLinkTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.manager = get_user_model().objects.create_user(
            email='disk-manager@example.com',
            password='test-password',
            is_staff=True,
        )
        self.client.force_login(self.manager)
        self.crm_client = Client.objects.create(
            company=self.company,
            manager=self.manager,
            full_name='Иванов Иван Иванович',
            phone='+99361111111',
            sl_id='SL-2027-001',
            academic_year=2027,
        )
        self.submission = OnboardingSubmission.objects.create(
            access_token_hash='test-token-hash',
            kind=OnboardingSubmission.KIND_APPLICANT,
            academic_year=2027,
            full_name=self.crm_client.full_name,
            phone=self.crm_client.phone,
            client=self.crm_client,
        )

    @override_settings(DISK_WEB_URL='https://disk.manager-sl.ru/web/client/login')
    def test_successful_provisioning_opens_exact_client_folder(self):
        root = self.create_disk_step()

        url, ready = build_client_disk_url(self.crm_client)

        self.assertTrue(ready)
        self.assertEqual(urlsplit(url).path, '/web/client/files')
        self.assertEqual(parse_qs(urlsplit(url).query)['path'], ['/' + root.rstrip('/')])

    def create_disk_step(self):
        root = '2027/Контракт/Иванов Иван Иванович (SL-2027-001)/'
        ClientProvisioningStep.objects.create(
            submission=self.submission,
            client=self.crm_client,
            step=ClientProvisioningStep.STEP_DISK,
            status=ClientProvisioningStep.STATUS_SUCCESS,
            event_id='disk-link-test',
            response_data={'root': root},
        )
        return root

    @override_settings(DISK_WEB_URL='https://disk.manager-sl.ru/web/client/login')
    def test_unprovisioned_client_opens_disk_login(self):
        url, ready = build_client_disk_url(self.crm_client)

        self.assertFalse(ready)
        self.assertEqual(url, 'https://disk.manager-sl.ru/web/client/login')

    @override_settings(
        DISK_PROVISION_API_URL='https://disk.manager-sl.ru/api/internal/disk/folders',
        DISK_PROVISION_SERVICE_TOKEN='disk-token',
    )
    @patch('apps.portal.views.requests.post')
    def test_manager_can_upload_supported_file_to_client_disk(self, post):
        self.create_disk_step()
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {
            'status': 'uploaded',
            'path': '/2027/Контракт/client/оригиналы/passport.pdf',
        }

        response = self.client.post(
            reverse('portal:client_disk_upload', args=[self.crm_client.pk]),
            {
                'folder': 'оригиналы',
                'file': SimpleUploadedFile('passport.pdf', b'%PDF-1.4\n%%EOF', content_type='application/pdf'),
            },
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('portal:client_detail', args=[self.crm_client.pk]),
            fetch_redirect_response=False,
        )
        post.assert_called_once()
        _args, kwargs = post.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer disk-token')
        self.assertEqual(kwargs['headers']['X-Actor'], 'disk-manager%40example.com')
        self.assertEqual(kwargs['headers']['X-Disk-Folder'], '%D0%BE%D1%80%D0%B8%D0%B3%D0%B8%D0%BD%D0%B0%D0%BB%D1%8B')

    @patch('apps.portal.views.requests.post')
    def test_manager_cannot_upload_unsupported_file(self, post):
        self.create_disk_step()

        response = self.client.post(
            reverse('portal:client_disk_upload', args=[self.crm_client.pk]),
            {
                'folder': 'оригиналы',
                'file': SimpleUploadedFile('script.exe', b'unsafe'),
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        post.assert_not_called()


class PortalClientChatTests(TestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(
            email='chat-manager@example.com',
            password='test-password',
            first_name='Мария',
            is_staff=True,
        )
        self.client.force_login(self.manager)

    @patch('apps.portal.views.AkylChatClient')
    def test_manager_can_open_client_chat(self, client_class):
        service = Mock()
        service.rooms.return_value = {
            'results': [{'id': 'room-1', 'sl_id': 'SL-001', 'user_name': 'Иван Иванов', 'unread_count': 1}]
        }
        service.messages.return_value = {
            'results': [{'id': 'message-1', 'text': 'Здравствуйте', 'is_mine': False}]
        }
        client_class.return_value = service

        response = self.client.get(reverse('portal:client_chats'), {'sl_id': 'SL-001'}, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иван Иванов')
        self.assertContains(response, 'Здравствуйте')
        service.mark_read.assert_called_once_with('SL-001')

    @patch('apps.portal.views.AkylChatClient')
    def test_manager_can_send_text_message(self, client_class):
        service = Mock()
        client_class.return_value = service

        response = self.client.post(
            reverse('portal:client_chats'),
            {'sl_id': 'SL-001', 'text': 'Проверка связи'},
            secure=True,
        )

        self.assertRedirects(
            response,
            f'{reverse("portal:client_chats")}?sl_id=SL-001',
            fetch_redirect_response=False,
        )
        service.send_message.assert_called_once_with(
            'SL-001', text='Проверка связи', upload=None, manager_name='Мария'
        )


class DashboardBirthdayGreetingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='birthday@example.com',
            password='test-password',
            first_name='Анна',
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_greeting_is_shown_on_users_birthday(self):
        today = timezone.localdate()
        self.user.dob = today.replace(year=today.year - 25)
        self.user.save(update_fields=['dob'])

        response = self.client.get(reverse('portal:dashboard'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'С днём рождения, Анна!')
        self.assertContains(response, 'Спасибо, что вы с нами.')

    def test_greeting_is_hidden_on_other_days(self):
        another_day = timezone.localdate() - timedelta(days=1)
        self.user.dob = another_day.replace(year=another_day.year - 25)
        self.user.save(update_fields=['dob'])

        response = self.client.get(reverse('portal:dashboard'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'С днём рождения, Анна!')


class PortalNotificationsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='notifications@example.com',
            password='test-password',
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_system_notification_without_sender_is_rendered(self):
        Notification.objects.create(
            recipient=self.user,
            sender=None,
            title='Системное уведомление',
            body='Тест',
        )

        response = self.client.get(reverse('portal:notifications'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Системное уведомление')
        self.assertContains(response, 'Система')


class PortalOnboardingWorkflowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.manager = get_user_model().objects.create_user(
            email='onboarding-manager@example.com',
            password='test-password',
            first_name='Мария',
            is_staff=True,
        )
        self.submission = OnboardingSubmission.objects.create(
            access_token_hash='test-token-hash',
            kind=OnboardingSubmission.KIND_SCHOOL_STUDENT,
            academic_year=2027,
            full_name='Тестовый Школьник',
            phone='+99361111111',
            payload={'school': 'Школа 1', 'school_class': '10'},
        )
        self.client.force_login(self.manager)

    def test_manager_can_open_incoming_submission(self):
        listing = self.client.get(reverse('portal:onboarding_submissions'), secure=True)
        detail = self.client.get(
            reverse('portal:onboarding_submission_detail', args=[self.submission.pk]),
            secure=True,
        )

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Тестовый Школьник')
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Школа 1')
        self.assertContains(detail, 'Взять на проверку')

    def test_manager_can_take_submission_into_review_from_portal(self):
        response = self.client.post(
            reverse('portal:onboarding_submission_review', args=[self.submission.pk]),
            {'decision': 'start_review'},
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('portal:onboarding_submission_detail', args=[self.submission.pk]),
            fetch_redirect_response=False,
        )
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, OnboardingSubmission.STATUS_IN_REVIEW)
        self.assertEqual(self.submission.reviewed_by, self.manager)
        self.assertTrue(
            OnboardingReviewEvent.objects.filter(
                submission=self.submission,
                decision=OnboardingReviewEvent.DECISION_START_REVIEW,
            ).exists()
        )

    @patch('apps.portal.views.enqueue_submission_sync', return_value=True)
    @patch('apps.portal.views.provision_client_services.delay')
    def test_approved_submission_shows_steps_and_retry_is_queued_once(
        self,
        provision_delay,
        enqueue_sheets,
    ):
        review_submission(
            self.submission,
            self.manager,
            OnboardingReviewEvent.DECISION_APPROVE,
        )
        self.submission.refresh_from_db()

        detail = self.client.get(
            reverse('portal:onboarding_submission_detail', args=[self.submission.pk]),
            secure=True,
        )
        retried = self.client.post(
            reverse('portal:onboarding_provisioning_retry', args=[self.submission.pk]),
            {'target': 'all'},
            secure=True,
        )

        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Подключение системы')
        self.assertContains(detail, 'Аккаунт Students Life')
        self.assertRedirects(
            retried,
            reverse('portal:onboarding_submission_detail', args=[self.submission.pk]),
            fetch_redirect_response=False,
        )
        provision_delay.assert_called_once()
        enqueue_sheets.assert_called_once_with(self.submission.pk)
