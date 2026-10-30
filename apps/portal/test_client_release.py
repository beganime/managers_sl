from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from django.urls import reverse
from apps.crm.models import Client
from apps.education.models import Country, University
from apps.portal.forms import PortalUniversityForm
from apps.client_api.serializers import ClientUniversitySerializer
from apps.organizations.models import Company
from django.contrib.auth import get_user_model


@override_settings(STUDENTS_LIFE_API_KEY='isolated-release-key')
class ClientReleaseTests(TestCase):
    def test_legacy_identity_status_and_conflict_are_safe(self):
        company = Company.objects.create(name='Test')
        manager = get_user_model().objects.create_user(email='test-manager@example.invalid')
        student = Client.objects.create(company=company, manager=manager, full_name='Test Student', custom_data={'mobile_user_id': '77'}, status='documents')
        api = APIClient()
        url = reverse('client_admission_status')
        self.assertEqual(api.get(url, {'mobile_user_id': 77}).status_code, 403)
        response = api.get(url, {'mobile_user_id': 77}, HTTP_X_API_KEY='isolated-release-key')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['client']['status'], 'documents')
        Client.objects.create(company=company, manager=manager, full_name='Other', mobile_app_user_id=77)
        self.assertEqual(api.get(url, {'mobile_user_id': 77}, HTTP_X_API_KEY='isolated-release-key').status_code, 409)

    def test_university_fields_round_trip_preserves_custom_data(self):
        country = Country.objects.create(name='Test', code='TS')
        university = University.objects.create(name='Test', country=country, custom_data={'keep': 1})
        form = PortalUniversityForm({'name': 'Test', 'country': country.pk, 'is_active': True, 'languages': 'Русский, английский', 'education_levels': 'Бакалавриат', 'dormitory_info': 'Есть общежитие'}, instance=university)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.custom_data['keep'], 1)
        serializer = ClientUniversitySerializer()
        self.assertEqual(serializer.get_languages(saved), 'Русский, английский')
        self.assertEqual(serializer.get_education_levels(saved), 'Бакалавриат')
        self.assertEqual(saved.dormitory_info, 'Есть общежитие')
