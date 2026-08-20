from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.client_onboarding.models import ClientProvisioningStep, OnboardingSubmission
from apps.crm.models import Client, ClientFile
from apps.organizations.models import Company


@override_settings(
    LEADS_API_KEY='test-leads-key',
    DISK_PROVISION_API_URL='https://disk.test/api/internal/disk/folders',
    DISK_PROVISION_SERVICE_TOKEN='disk-token',
    DISK_WEB_URL='https://disk.manager-sl.ru/web/client/login',
    SECURE_SSL_REDIRECT=False,
)
class MobileDocumentUploadTests(TestCase):
    def setUp(self):
        manager = get_user_model().objects.create_user(
            email='manager@example.com',
            password='test-password',
        )
        company = Company.objects.create(name='Students Life')
        self.client_record = Client.objects.create(
            company=company,
            manager=manager,
            full_name='Иванов Иван Иванович',
            phone='+99360000000',
            mobile_app_user_id=999,
            mobile_app_source=True,
            sl_id='SL-2027-999',
            academic_year=2027,
            funding_type='contract',
        )
        self.submission = OnboardingSubmission.objects.create(
            access_token_hash=OnboardingSubmission.hash_access_token('token'),
            kind=OnboardingSubmission.KIND_APPLICANT,
            stage=OnboardingSubmission.STAGE_FULL,
            academic_year=2027,
            status=OnboardingSubmission.STATUS_APPROVED,
            full_name=self.client_record.full_name,
            phone=self.client_record.phone,
            client=self.client_record,
        )
        ClientProvisioningStep.objects.create(
            submission=self.submission,
            client=self.client_record,
            step=ClientProvisioningStep.STEP_DISK,
            status=ClientProvisioningStep.STATUS_SUCCESS,
            event_id='test:disk',
            response_data={'root': '2027/Контракт/Иванов Иван Иванович (SL-2027-999)'},
        )

    @patch('leads.views.requests.post')
    def test_upload_forwards_file_to_disk_and_creates_review_record(self, post_mock):
        disk_response = Mock()
        disk_response.raise_for_status.return_value = None
        disk_response.json.return_value = {
            'path': '2027/Контракт/Иванов Иван Иванович (SL-2027-999)/оригиналы/passport.pdf',
        }
        post_mock.return_value = disk_response

        response = self.client.post(
            '/api/mobile/documents/upload/',
            data=b'%PDF-1.4\n%%EOF',
            content_type='application/pdf',
            HTTP_X_API_KEY='test-leads-key',
            HTTP_X_MOBILE_DOCUMENT_ID='77',
            HTTP_X_MOBILE_USER_ID='999',
            HTTP_X_SL_ID='SL-2027-999',
            HTTP_X_DOCUMENT_TITLE='Passport',
            HTTP_X_FILE_NAME='passport.pdf',
        )

        self.assertEqual(response.status_code, 200)
        document = ClientFile.objects.get(external_mobile_document_id=77)
        self.assertEqual(document.client, self.client_record)
        self.assertEqual(document.status, ClientFile.STATUS_PENDING)
        self.assertIn('DiskSL:', document.comment)
        self.assertIn('path=', document.external_file_url)
        forwarded_headers = post_mock.call_args.kwargs['headers']
        self.assertEqual(forwarded_headers['X-Disk-Folder'], '%D0%BE%D1%80%D0%B8%D0%B3%D0%B8%D0%BD%D0%B0%D0%BB%D1%8B')

    def test_upload_requires_service_key(self):
        response = self.client.post(
            '/api/mobile/documents/upload/',
            data=b'%PDF-1.4\n%%EOF',
            content_type='application/pdf',
        )
        self.assertEqual(response.status_code, 403)
