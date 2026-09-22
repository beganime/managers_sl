from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.portal.views import ClientDetailView, ClientExamsPanelView, get_client_exams_from_students_life


class ClientExamsPanelTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True)

    @patch('apps.portal.views.get_client_exams_from_students_life')
    @patch('apps.portal.views.get_object_or_404')
    @patch('apps.portal.views.client_queryset')
    def test_panel_uses_scoped_client_and_short_timeout(self, client_queryset, get_object, get_exams):
        client = SimpleNamespace(mobile_app_user_id=42)
        get_object.return_value = client
        get_exams.return_value = (True, [{'subject': 'Математика'}], '')
        request = self.factory.get('/portal/clients/7/exams/list/')
        request.user = self.user

        response = ClientExamsPanelView.as_view()(request, pk=7)

        get_object.assert_called_once_with(client_queryset.return_value, pk=7)
        get_exams.assert_called_once_with(client, timeout=5)
        self.assertContains(response, 'Математика')
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    @patch('apps.portal.views.get_client_exams_from_students_life')
    @patch('apps.portal.views.get_object_or_404')
    @patch('apps.portal.views.client_queryset')
    def test_panel_skips_remote_request_without_mobile_account(self, client_queryset, get_object, get_exams):
        get_object.return_value = SimpleNamespace(mobile_app_user_id=None, custom_data={})
        request = self.factory.get('/portal/clients/7/exams/list/')
        request.user = self.user

        response = ClientExamsPanelView.as_view()(request, pk=7)

        self.assertContains(response, 'Экзамены пока не назначены')
        get_exams.assert_not_called()

    @patch('apps.portal.views.students_life_api_request', return_value=(False, ['invalid response']))
    def test_unexpected_exam_error_payload_does_not_crash(self, api_request):
        client = SimpleNamespace(mobile_app_user_id=42)

        ok, exams, error = get_client_exams_from_students_life(client, timeout=5)

        self.assertFalse(ok)
        self.assertEqual(exams, [])
        self.assertIn('Не удалось получить', error)
        self.assertEqual(api_request.call_args.kwargs['timeout'], 5)

    @patch('apps.portal.views.get_client_exams_from_students_life')
    @patch('apps.portal.views.ExternalAccount.objects.filter')
    @patch('apps.portal.views.document_queryset')
    @patch('apps.portal.views.deal_queryset')
    @patch('apps.portal.views.application_queryset')
    @patch('apps.portal.views.mailbox_overview', return_value=[])
    @patch('apps.portal.views.build_client_disk_url', return_value=('/disk/', False))
    @patch('apps.portal.views.build_student_360', return_value={})
    @patch('apps.portal.views.can_access_disk', return_value=False)
    @patch('apps.portal.views.is_erp_admin', return_value=True)
    @patch('apps.portal.views.PortalContextMixin.get_context_data', return_value={})
    @patch('apps.portal.views.ClientDetailView.get_client')
    def test_main_card_does_not_wait_for_exam_service(
        self, get_client, _base_context, _is_admin, _can_access_disk,
        _student_360, _disk_url, _mailbox, _applications, _deals,
        _documents, _external_accounts, get_exams,
    ):
        get_client.return_value = SimpleNamespace(
            pk=7, sl_id='SL-2027-007', manager_id=1,
            mobile_app_user_id=42, custom_data={},
        )
        request = self.factory.get('/portal/clients/7/')
        request.user = SimpleNamespace(pk=1, is_authenticated=True, is_superuser=True)
        view = ClientDetailView()
        view.request = request

        context = view.get_context_data()

        self.assertEqual(context['mobile_user_id'], 42)
        get_exams.assert_not_called()
