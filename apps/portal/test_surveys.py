from django.test import SimpleTestCase
from django.urls import resolve
from django.template.loader import get_template
from .survey_views import SurveyForm, ClientFormsView


class SurveyTests(SimpleTestCase):
    def test_url_and_limits(self):
        data = {'title': 'Test', 'form_url': 'https://forms.gle/abc', 'status': 'draft'}
        self.assertTrue(SurveyForm(data).is_valid())
        for url in ('http://forms.gle/abc', 'https://docs.google.com/forms/d/abc/edit', 'https://forms.gle.evil/a', 'https://user@forms.gle/a'):
            self.assertFalse(SurveyForm({**data, 'form_url': url}).is_valid())
        self.assertFalse(SurveyForm({**data, 'description': 'a'*1001}).is_valid())

    def test_route_and_template(self):
        self.assertEqual(resolve('/portal/client-polls/').func.view_class, ClientFormsView)
        get_template('portal/client_forms.html')
