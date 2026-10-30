from types import SimpleNamespace
from unittest.mock import patch
from django.core.exceptions import PermissionDenied
from django.template.loader import get_template
from django.test import SimpleTestCase, RequestFactory
from django.urls import reverse
from .poll_views import PollForm, ClientPollsView


class PollPortalTests(SimpleTestCase):
    def test_form_options(self):
        data = {'question': 'Вопрос', 'options': 'Россия\nКитай', 'status': 'published'}
        form = PollForm(data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['options'], ['Россия', 'Китай'])
        for value in ('One', 'One\none', 'x' * 256 + '\nB'):
            self.assertFalse(PollForm({**data, 'options': value}).is_valid())

    def test_admin_only(self):
        request = RequestFactory().post('/')
        request.user = SimpleNamespace(is_authenticated=True)
        with patch('apps.portal.content_views.is_erp_admin', return_value=False):
            with self.assertRaises(PermissionDenied):
                ClientPollsView.as_view()(request)

    def test_template_route(self):
        get_template('portal/client_polls.html')
        self.assertTrue(reverse('portal:client_polls'))
