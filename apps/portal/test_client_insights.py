from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase, RequestFactory, override_settings
from apps.crm.models import Client, ActivityLog
from apps.organizations.models import Company
from .models import ClientMotivationProfile
from .client_insights import MotivationForm, MotivationEditView, ClientTrackSummaryView


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class ClientInsightsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='insights@example.test', password='test-only')
        self.other = get_user_model().objects.create_user(email='other@example.test', password='test-only')
        self.company = Company.objects.create(name='Synthetic insights')
        self.student = Client.objects.create(company=self.company, manager=self.user, full_name='Synthetic', phone='')
        self.factory = RequestFactory()

    def request(self, data=None, user=None):
        req = self.factory.post('/portal/clients/1/motivation/', data) if data is not None else self.factory.get('/', HTTP_HX_REQUEST='true')
        req.user = user or self.user
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def test_limits_and_choices(self):
        for data in ({'talents': 'a'*1001}, {'next_question': 'a'*256}, {'track': 'invalid'}):
            self.assertFalse(MotivationForm(data).is_valid())
        self.assertTrue(MotivationForm({'talents': 'a'*1000}).is_valid())

    def test_save_and_audit(self):
        response = MotivationEditView.as_view()(self.request({'track': 'medical', 'hobbies': 'Chess'}), pk=self.student.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ClientMotivationProfile.objects.get(client=self.student).hobbies, 'Chess')
        self.assertTrue(ActivityLog.objects.filter(student=self.student, action='CLIENT_MOTIVATION_UPDATED').exists())

    def test_stale_save_preserves_answers(self):
        profile = ClientMotivationProfile.objects.create(client=self.student, hobbies='Original')
        response = MotivationEditView.as_view()(self.request({'hobbies': 'Overwrite', 'revision': ''}), pk=self.student.pk)
        self.assertEqual(response.status_code, 400)
        profile.refresh_from_db()
        self.assertEqual(profile.hobbies, 'Original')

    def test_current_revision_can_update(self):
        profile = ClientMotivationProfile.objects.create(client=self.student, hobbies='Original')
        response = MotivationEditView.as_view()(self.request({'hobbies': 'Updated', 'revision': profile.updated_at.isoformat()}), pk=self.student.pk)
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.hobbies, 'Updated')

    def test_empty_questionnaire_renders(self):
        response = MotivationEditView.as_view()(self.request(), pk=self.student.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="revision"')

    def test_private_student_is_hidden(self):
        with self.assertRaises(Http404):
            MotivationEditView.as_view()(self.request(user=self.other), pk=self.student.pk)

    def test_visible_nonowner_cannot_edit(self):
        with patch('apps.portal.views.client_queryset', return_value=Client.objects.all()):
            with self.assertRaises(PermissionDenied):
                MotivationEditView.as_view()(self.request({'track': 'it'}, self.other), pk=self.student.pk)

    def test_summary_scope_and_archive(self):
        ClientMotivationProfile.objects.create(client=self.student, track='medical')
        Client.objects.create(company=self.company, manager=self.user, full_name='Archived', phone='', status='archive')
        Client.objects.create(company=self.company, manager=self.other, full_name='Hidden', phone='')
        with patch('apps.portal.client_insights.render') as render:
            ClientTrackSummaryView.as_view()(self.request())
            context = render.call_args.args[2]
            self.assertEqual(context['track_total'], 1)
            self.assertEqual(context['track_rows'][0]['count'], 1)
            ClientTrackSummaryView.as_view()(self.request(user=self.other))
            context = render.call_args.args[2]
            self.assertEqual(context['track_rows'][0]['count'], 0)
            self.assertEqual(context['track_rows'][-1]['count'], 1)

    def test_fragment_escapes_answers(self):
        ClientMotivationProfile.objects.create(client=self.student, hobbies='<script>alert(1)</script>')
        response = MotivationEditView.as_view()(self.request(), pk=self.student.pk)
        self.assertContains(response, '&lt;script&gt;')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
