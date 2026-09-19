from types import SimpleNamespace

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase

from students_life.error_views import page_not_found, permission_denied


class ErrorPageTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_permission_page_explains_admin_access(self):
        request = self.factory.get('/portal/reports/employees/')
        request.user = SimpleNamespace(is_authenticated=True)

        response = permission_denied(
            request,
            PermissionDenied('Отчёты сотрудников доступны только администратору.'),
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Войти как администратор', status_code=403)
        self.assertContains(response, 'Вернуться назад', status_code=403)
        self.assertContains(response, 'Отчёты сотрудников доступны только администратору.', status_code=403)

    def test_api_errors_stay_json(self):
        request = self.factory.get('/api/unknown/', HTTP_ACCEPT='application/json')
        request.user = SimpleNamespace(is_authenticated=False)

        response = page_not_found(request, Exception('missing'))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertJSONEqual(response.content, {'detail': 'Такого адреса больше нет', 'status': 404})
