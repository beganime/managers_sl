from django.test import SimpleTestCase
from apps.portal.views import build_mobile_nav
from apps.client_onboarding.services import split_person_name, latin_name


class NavigationRefreshTests(SimpleTestCase):
    def test_only_current_main_item_is_active(self):
        for page in ('dashboard', 'clients', 'workday'):
            active = [item['name'] for item in build_mobile_nav(page) if item['is_active']]
            self.assertEqual(active, [page])

    def test_given_name_not_surname(self):
        given, _ = split_person_name('Иванов Иван Иванович')
        self.assertEqual(f'{latin_name(given).capitalize()}_0710', 'Ivan_0710')
