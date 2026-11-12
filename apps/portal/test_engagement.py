from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone
from apps.organizations.models import Company
from apps.employees.models import EmployeeProfile, EmployeeRole
from .engagement import daily_context, SuggestionView, StaffMetricsView, SuggestionsAdminView
from .models import StaffSuggestion, PortalPresence
from .views import can_manage_catalog, UniversitiesView, ProgramsView, build_nav_groups
from apps.education.models import University
from unittest.mock import MagicMock
from django.http import Http404
from .engagement import MoodSupportView, mood_support_context
from .models import EmployeeMood, MoodSupport


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class EngagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email='team@example.test', password='test-only', role='manager')
        self.admin = get_user_model().objects.create_user(email='admin@example.test', password='test-only', role='admin')
        role = EmployeeRole.objects.create(code='testmanager', name='Менеджер', role_type='manager')
        self.profile = EmployeeProfile.objects.create(user=self.user, company=Company.objects.create(name='Synthetic'), role=role)
        self.factory = RequestFactory()

    def request(self, user=None, data=None):
        req = self.factory.get('/') if data is None else self.factory.post('/', data)
        req.user = user or self.user
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def test_catalog_manager_and_viewer(self):
        self.assertTrue(can_manage_catalog(self.user))
        self.profile.role.role_type = 'viewer'
        self.profile.role.save()
        self.assertFalse(can_manage_catalog(self.user))

    def test_inactive_manager_denied(self):
        self.profile.work_status = 'fired'
        self.profile.save()
        self.assertFalse(can_manage_catalog(self.user))

    def test_navigation(self):
        names = {item['name'] for group in build_nav_groups(self.user, 'dashboard') for item in group['items']}
        self.assertTrue({'client_content', 'universities', 'programs'} <= names)
        self.assertFalse({'staff_metrics', 'staff_suggestions'} & names)

    def test_catalog_get_pages_and_presence(self):
        for view in (UniversitiesView, ProgramsView):
            response = view.as_view()(self.request())
            self.assertEqual(response.status_code, 200)
            response.render()
        self.assertEqual(PortalPresence.objects.get(user=self.user).section, 'Программы')

    def test_daily_prompt_once(self):
        self.assertTrue(daily_context(self.user)['ask_suggestion'])
        self.assertFalse(daily_context(self.user)['ask_suggestion'])
        tomorrow = timezone.localdate() + timedelta(days=1)
        with patch('apps.portal.engagement.timezone.localdate', return_value=tomorrow):
            self.assertTrue(daily_context(self.user)['ask_suggestion'])
        self.assertNotIn('ask_suggestion', daily_context(self.admin))

    def test_attendance_opt_in_admin_is_counted(self):
        self.user.role = 'admin'
        self.user.save()
        self.profile.attendance_required = True
        self.profile.save()
        view = StaffMetricsView()
        view.setup(self.request(user=self.admin))
        row = next(r for r in view.get_context_data()['rows'] if r['person'].user_id == self.user.pk)
        self.assertFalse(row['admin'])

    @override_settings(ATTENDANCE_TELEGRAM_ENABLED=True)
    def test_support_notice_personal_and_deduplicated(self):
        from apps.attendance.models import EmployeeTelegramAccount, AttendanceTelegramDelivery
        EmployeeTelegramAccount.objects.create(employee=self.user, telegram_user_id=123, chat_id=123)
        mood = EmployeeMood.objects.create(user=self.user, date=timezone.localdate(), slot=1, score=1)
        with patch('apps.attendance.telegram._enqueue') as enqueue:
            for data in ({'action': 'like', 'liked': '1'}, {'action': 'like', 'liked': '1'}, {'action': 'like', 'liked': '0'}, {'action': 'like', 'liked': '1'}, {'action': 'comment', 'comment': 'Держись'}, {'action': 'comment', 'comment': 'Правка'}):
                MoodSupportView.as_view()(self.request(user=self.admin, data=data), pk=mood.pk)
            self.assertEqual(enqueue.call_count, 2)
        deliveries = AttendanceTelegramDelivery.objects.filter(event_type='mood_support')
        self.assertEqual(deliveries.count(), 2)
        self.assertEqual(set(deliveries.values_list('target_chat_id', flat=True)), {123})

    @override_settings(ATTENDANCE_TELEGRAM_ENABLED=True)
    def test_support_notice_no_group_fallback(self):
        from apps.attendance.models import AttendanceTelegramDelivery
        mood = EmployeeMood.objects.create(user=self.user, date=timezone.localdate(), slot=1, score=1)
        MoodSupportView.as_view()(self.request(user=self.admin, data={'action': 'like', 'liked': '1'}), pk=mood.pk)
        self.assertFalse(AttendanceTelegramDelivery.objects.exists())

    def test_support_is_idempotent_and_preserves_comment(self):
        mood = EmployeeMood.objects.create(user=self.user, date=timezone.localdate(), slot=1, score=1)
        for data in ({'action': 'comment', 'comment': 'Держись!'}, {'action': 'like', 'liked': '1'}, {'action': 'like', 'liked': '1'}):
            self.assertEqual(MoodSupportView.as_view()(self.request(data=data), pk=mood.pk).status_code, 302)
        self.assertEqual(MoodSupport.objects.count(), 1)
        row = MoodSupport.objects.get()
        self.assertTrue(row.liked)
        self.assertEqual(row.comment, 'Держись!')
        self.assertEqual(mood_support_context(self.user)[0]['likes'], 1)

    def test_support_limits_and_scope(self):
        mood = EmployeeMood.objects.create(user=self.user, date=timezone.localdate(), slot=1, score=2)
        MoodSupportView.as_view()(self.request(data={'action': 'comment', 'comment': 'a'*501}), pk=mood.pk)
        self.assertFalse(MoodSupport.objects.exists())
        self.profile.company = Company.objects.create(name='Different company')
        self.profile.save()
        outsider = get_user_model().objects.create_user(email='outsider@example.test', password='test-only')
        EmployeeProfile.objects.create(user=outsider, company=Company.objects.create(name='Outside'), role=self.profile.role)
        with self.assertRaises(Http404):
            MoodSupportView.as_view()(self.request(user=outsider, data={'action': 'like', 'liked': '1'}), pk=mood.pk)
        mood.score = 5
        mood.save()
        with self.assertRaises(Http404):
            MoodSupportView.as_view()(self.request(data={'action': 'like', 'liked': '1'}), pk=mood.pk)

    def test_support_template_escapes_comments(self):
        from django.template.loader import render_to_string
        mood = EmployeeMood.objects.create(user=self.user, date=timezone.localdate(), slot=1, score=2)
        MoodSupport.objects.create(user=self.user, mood=mood, comment='<script>bad()</script>')
        html = render_to_string('portal/partials/mood_support.html', {'support_moods': mood_support_context(self.user)})
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>bad()', html)

    def test_edit_keeps_global_university_scope(self):
        university = University(name='Synthetic global')
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = university
        view = UniversitiesView()
        with patch.object(view, 'get_edit_object', return_value=university), patch.object(view, 'get_form', return_value=form), patch.object(university, 'save'):
            response = view.post(self.request(data={'name': 'Updated'}))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(university.company_id)

    def test_create_assigns_manager_company(self):
        university = University(name='Synthetic new')
        form = MagicMock()
        form.is_valid.return_value = True
        form.save.return_value = university
        view = UniversitiesView()
        with patch.object(view, 'get_edit_object', return_value=None), patch.object(view, 'get_form', return_value=form), patch.object(university, 'save'):
            self.assertEqual(view.post(self.request(data={'name': 'New'})).status_code, 302)
        self.assertEqual(university.company_id, self.profile.company_id)

    def test_suggestion_submission_deduplicated(self):
        for text in ('Добавьте поиск', 'Не перезаписывать'):
            self.assertEqual(SuggestionView.as_view()(self.request(data={'text': text})).status_code, 302)
        self.assertEqual(StaffSuggestion.objects.get(user=self.user).text, 'Добавьте поиск')

    def test_long_suggestion_rejected(self):
        response = SuggestionView.as_view()(self.request(data={'text': 'a' * 1001}))
        self.assertEqual(response.status_code, 400)
        response.render()
        self.assertFalse(StaffSuggestion.objects.exists())

    def test_admin_pages_reject_staff_manager(self):
        self.user.is_staff = True
        self.user.save()
        for view in (StaffMetricsView, SuggestionsAdminView):
            with self.assertRaises(PermissionDenied):
                view.as_view()(self.request())

    def test_admin_pages_render_and_escape(self):
        StaffSuggestion.objects.create(user=self.user, date=timezone.localdate(), text='<script>alert(1)</script>', submitted_at=timezone.now())
        for view in (StaffMetricsView, SuggestionsAdminView):
            response = view.as_view()(self.request(user=self.admin))
            self.assertEqual(response.status_code, 200)
            response.render()
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
