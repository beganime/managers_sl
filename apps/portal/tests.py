import base64
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.client_onboarding.models import ClientProvisioningStep, OnboardingReviewEvent, OnboardingSubmission
from apps.client_onboarding.services import review_submission
from apps.crm.credentials import decrypt_external_secret
from apps.crm.models import ActivityLog, Application, ApplicationStageHistory, Client, ClientNote, ExternalAccount
from apps.erp_notifications.models import Notification
from apps.organizations.models import Company
from apps.portal.views import build_client_disk_url, build_questionnaire_sections
from users.disk_auth import verify_disk_sso_ticket


class QuestionnairePresentationTests(TestCase):
    def test_api_field_names_are_not_shown_to_managers(self):
        sections = build_questionnaire_sections({
            'funding_type': 'government',
            'requested_services': ['Подбор вуза'],
            'desired_universities': 'БГМУ / РУДН',
            'unknown_mobile_flag': 'Значение',
        })
        labels = [row['label'] for section in sections for row in section['rows']]
        values = [row['value'] for section in sections for row in section['rows']]

        self.assertIn('Форма поступления', labels)
        self.assertIn('Нужные услуги', labels)
        self.assertIn('Желаемые вузы', labels)
        self.assertIn('Дополнительное поле', labels)
        self.assertIn('Гослиния', values)
        self.assertNotIn('funding_type', labels)
        self.assertNotIn('unknown_mobile_flag', labels)


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
        self.assertEqual(urlsplit(url).path, reverse('portal:disk_sl'))
        next_url = parse_qs(urlsplit(url).query)['next'][0]
        self.assertEqual(urlsplit(next_url).path, '/web/client/files')
        self.assertEqual(parse_qs(urlsplit(next_url).query)['path'], ['/' + root.rstrip('/')])

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
        self.assertEqual(url, reverse('portal:disk_sl'))

    @override_settings(DISK_WEB_URL='https://disk.manager-sl.ru/web/client/login')
    @patch('apps.portal.views.requests.get')
    def test_manager_opens_disk_without_reentering_password(self, get):
        get.return_value.raise_for_status.return_value = None
        get.return_value.text = '<input type="hidden" name="_form_token" value="sftpgo-csrf">'

        response = self.client.get(
            reverse('portal:disk_sl'),
            {'next': '/web/client/files?path=%2F2027'},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sftpgo-csrf')
        ticket = response.context['disk_ticket']
        self.assertLessEqual(len(ticket.encode()), 72)
        self.assertTrue(verify_disk_sso_ticket(self.manager.email, ticket))

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

    @override_settings(
        TRANSLATE_SL_PATH_URL='/translate',
        TRANSLATE_SL_SSO_SECRET='shared-test-secret',
    )
    def test_manager_opens_translate_sl_with_signed_identity_and_client(self):
        response = self.client.get(
            reverse('portal:translate_sl'),
            {'next': '/upload/?client=SL-2027-001'},
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        target = urlsplit(response.url)
        self.assertEqual(target.path, '/translate/accounts/manager-sl/')
        token = parse_qs(target.query)['token'][0]
        payload = signing.loads(
            token,
            key='shared-test-secret',
            salt='manager-sl.translate-sso.v1',
            max_age=120,
        )
        self.assertEqual(payload['email'], self.manager.email)
        self.assertEqual(payload['next'], '/upload/?client=SL-2027-001')

    @override_settings(
        TRANSLATE_SL_PATH_URL='/translate',
        TRANSLATE_SL_SSO_SECRET='shared-test-secret',
    )
    def test_translate_sl_redirect_rejects_external_next_url(self):
        response = self.client.get(
            reverse('portal:translate_sl'),
            {'next': 'https://example.net/stolen'},
            secure=True,
        )

        token = parse_qs(urlsplit(response.url).query)['token'][0]
        payload = signing.loads(
            token,
            key='shared-test-secret',
            salt='manager-sl.translate-sso.v1',
            max_age=120,
        )
        self.assertEqual(payload['next'], '/')


class ApplicationWorkflowPortalTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Workflow portal company')
        self.manager = get_user_model().objects.create_user(
            email='workflow-portal@example.invalid',
            password='test-password',
            is_staff=True,
        )
        self.crm_client = Client.objects.create(
            company=self.company,
            manager=self.manager,
            full_name='Workflow Portal Student',
            phone='+00000000001',
        )
        self.application = Application.objects.create(
            client=self.crm_client,
            company=self.company,
            manager=self.manager,
            university_name='Test University',
            program_name='Test Program',
        )
        self.client.force_login(self.manager)

    def test_manager_transitions_scoped_application_and_writes_audit(self):
        response = self.client.post(
            reverse('portal:application_transition', args=[self.crm_client.pk, self.application.pk]),
            {'stage': Application.STAGE_APPLICATION_PREPARATION, 'comment': 'Документы проверены'},
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('portal:client_detail', args=[self.crm_client.pk]),
            fetch_redirect_response=False,
        )
        self.application.refresh_from_db()
        self.assertEqual(self.application.current_stage, Application.STAGE_APPLICATION_PREPARATION)
        self.assertEqual(ApplicationStageHistory.objects.filter(application=self.application).count(), 1)
        self.assertEqual(ActivityLog.objects.filter(application=self.application).count(), 1)

    def test_application_from_another_client_is_not_disclosed(self):
        another_client = Client.objects.create(
            company=self.company,
            manager=self.manager,
            full_name='Another Student',
            phone='+00000000002',
        )

        response = self.client.post(
            reverse('portal:application_transition', args=[another_client.pk, self.application.pk]),
            {'stage': Application.STAGE_APPLICATION_PREPARATION},
            secure=True,
        )

        self.assertEqual(response.status_code, 404)

    def test_manager_adds_shared_note_from_client_card(self):
        response = self.client.post(
            reverse('portal:client_note_create', args=[self.crm_client.pk]),
            {'text': 'Позвонить клиенту после 15:00'},
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('portal:client_detail', args=[self.crm_client.pk]),
            fetch_redirect_response=False,
        )
        note = ClientNote.objects.get(client=self.crm_client)
        self.assertEqual(note.author, self.manager)
        self.assertFalse(note.is_private)
        self.assertTrue(ActivityLog.objects.filter(
            student=self.crm_client, action='CLIENT_NOTE_CREATED',
        ).exists())

    def test_client_note_rejects_more_than_1000_characters(self):
        response = self.client.post(
            reverse('portal:client_note_create', args=[self.crm_client.pk]),
            {'text': 'x' * 1001},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ClientNote.objects.exists())

    def test_staff_manager_does_not_see_another_managers_private_note(self):
        other = get_user_model().objects.create_user(
            email='other-note-author@example.invalid', password='test-password', is_staff=True,
        )
        ClientNote.objects.create(
            client=self.crm_client, author=other, text='Скрытая заметка другого менеджера', is_private=True,
        )
        ClientNote.objects.create(
            client=self.crm_client, author=other, text='Общая заметка', is_private=False,
        )

        response = self.client.get(
            reverse('portal:client_detail', args=[self.crm_client.pk]), secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Скрытая заметка другого менеджера')
        self.assertContains(response, 'Общая заметка')


PORTAL_EXTERNAL_KEY = base64.urlsafe_b64encode(b'portal-external-account-key-32by').decode('ascii')


@override_settings(EXTERNAL_ACCOUNT_ENCRYPTION_KEY=PORTAL_EXTERNAL_KEY)
class ExternalAccountPortalTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='External portal company')
        self.manager = get_user_model().objects.create_user(
            email='external-portal@example.invalid', password='test-password', is_staff=True,
        )
        self.student = Client.objects.create(
            company=self.company, manager=self.manager, full_name='RUID Student',
            phone='+00000000020', sl_id='SL-002',
        )
        self.application = Application.objects.create(
            client=self.student, company=self.company, manager=self.manager,
            university_name='RUID University', program_name='Medicine',
        )
        self.client.force_login(self.manager)

    def test_create_external_account_from_student_card_encrypts_secret(self):
        response = self.client.post(
            reverse('portal:external_account_create', args=[self.student.pk]),
            {
                'system': ExternalAccount.SYSTEM_RUID,
                'provider_name': 'RUID',
                'application': self.application.pk,
                'portal_url': 'https://example.invalid/ruid',
                'email': 'ruid@example.invalid',
                'login': 'SL002',
                'secret': 'portal-password',
                'status': ExternalAccount.STATUS_CREATED,
            },
            secure=True,
        )

        self.assertRedirects(
            response, reverse('portal:client_detail', args=[self.student.pk]),
            fetch_redirect_response=False,
        )
        account = ExternalAccount.objects.get()
        self.assertNotIn('portal-password', account.secret_ciphertext)
        self.assertEqual(decrypt_external_secret(account.secret_ciphertext), 'portal-password')
        self.assertEqual(ActivityLog.objects.get().action, 'EXTERNAL_ACCOUNT_CREATED')

    def test_secret_page_requires_dedicated_permission_and_is_not_cached(self):
        self.client.post(
            reverse('portal:external_account_create', args=[self.student.pk]),
            {
                'system': ExternalAccount.SYSTEM_RUID,
                'provider_name': 'RUID',
                'secret': 'portal-password',
                'status': ExternalAccount.STATUS_CREATED,
            },
            secure=True,
        )
        account = ExternalAccount.objects.get()
        url = reverse('portal:external_account_secret', args=[self.student.pk, account.pk])

        denied = self.client.post(url, secure=True)
        self.assertEqual(denied.status_code, 404)

        permission = Permission.objects.get(codename='view_externalaccount_secret')
        self.manager.user_permissions.add(permission)
        self.manager = get_user_model().objects.get(pk=self.manager.pk)
        self.client.force_login(self.manager)
        allowed = self.client.post(url, secure=True)
        self.assertEqual(allowed.status_code, 200)
        self.assertContains(allowed, 'portal-password')
        self.assertIn('no-store', allowed['Cache-Control'])
        self.assertEqual(allowed['Referrer-Policy'], 'no-referrer')
        viewed = ActivityLog.objects.get(action='EXTERNAL_ACCOUNT_SECRET_VIEWED')
        self.assertEqual(viewed.actor, self.manager)
        self.assertNotIn('portal-password', str(viewed.metadata))


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
    def test_manager_can_search_chat_by_name_or_sl_id(self, client_class):
        service = Mock()
        service.rooms.return_value = {
            'results': [
                {'id': 'room-1', 'sl_id': 'SL-001', 'user_name': 'Иван Иванов'},
                {'id': 'room-2', 'sl_id': 'SL-008', 'user_name': 'Анна Петрова'},
            ]
        }
        service.messages.return_value = {'results': []}
        client_class.return_value = service

        by_name = self.client.get(reverse('portal:client_chats'), {'q': 'Анна'}, secure=True)
        self.assertContains(by_name, 'Анна Петрова')
        self.assertNotContains(by_name, 'Иван Иванов')

        by_id = self.client.get(reverse('portal:client_chats'), {'q': 'SL-001'}, secure=True)
        self.assertContains(by_id, 'Иван Иванов')
        self.assertNotContains(by_id, 'Анна Петрова')

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
