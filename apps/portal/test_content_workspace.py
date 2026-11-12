from types import SimpleNamespace
from unittest.mock import patch
from django.core.exceptions import PermissionDenied
from django.template.loader import get_template
from django.test import SimpleTestCase, RequestFactory
from django.urls import reverse
from .content_views import ClientContentView, CatalogRemoveView, NewsForm
from .views import UniversitiesView, ProgramsView


class ContentWorkspaceTests(SimpleTestCase):
    def test_employee_cannot_manage_content(self):
        request = RequestFactory().post('/')
        request.user = SimpleNamespace(is_authenticated=True)
        for view in (ClientContentView, CatalogRemoveView):
            with patch('apps.portal.content_views.is_erp_admin', return_value=False):
                with self.assertRaises(PermissionDenied):
                    view.as_view()(request, kind='university', pk=1)
        for view in (UniversitiesView, ProgramsView):
            with patch('apps.portal.views.is_erp_admin', return_value=False):
                with self.assertRaises(PermissionDenied):
                    view.as_view()(request)

    def test_archive_preserves_record(self):
        request = RequestFactory().post('/')
        from apps.education.models import Program
        item = Program(name='Test')
        view = CatalogRemoveView()
        with patch.object(view, 'get_object', return_value=item), patch.object(item, 'save') as save, patch('apps.portal.content_views.messages.success'):
            response = view.post(request)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(item.is_active)
        self.assertTrue(item.is_archived)
        save.assert_called_once()

    def test_templates_and_routes(self):
        for name in ('client_content', 'client_news', 'news_edit', 'news_delete', 'content_remove'):
            get_template('portal/' + name + '.html')
        self.assertTrue(reverse('portal:client_content'))
        self.assertTrue(reverse('portal:news_edit', args=[1]))

    def test_news_limits(self):
        form = NewsForm({'title': 'x' * 256, 'content_markdown': 'text', 'status': 'published'})
        self.assertFalse(form.is_valid())
        self.assertIn('title', form.errors)
