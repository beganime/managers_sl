from django.urls import reverse
from rest_framework.test import APITestCase

from apps.education.models import City, Country, Program, University


class EducationCatalogApiTests(APITestCase):
    def setUp(self):
        country = Country.objects.create(name='Россия', code='RU')
        city = City.objects.create(country=country, name='Москва')
        self.university = University.objects.create(
            country=country,
            city=city,
            name='Московский авиационный институт',
        )
        self.program = Program.objects.create(
            university=self.university,
            name='БЮДЖЕТ: Прикладная математика и информатика (Математическое моделирование)',
        )

    def test_program_catalog_returns_priority_offer_and_service_price(self):
        response = self.client.get(reverse('client-program-list'), {'search': 'Прикладная математика'})

        self.assertEqual(response.status_code, 200, response.data)
        program = response.data['results'][0]
        self.assertEqual(program['priority_offer']['code'], '01.03.02')
        self.assertEqual(program['priority_offer']['service_fee_usd'], 3000)
        self.assertEqual(program['fees'][0]['source'], 'Гослиния')

    def test_university_can_be_found_by_generated_abbreviation(self):
        self.assertEqual(self.university.abbreviation, 'МАИ')

        response = self.client.get(reverse('client-university-list'), {'search': 'МАИ'})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'][0]['id'], self.university.id)

    def test_priority_price_catalog_has_search_and_no_duplicate_rows(self):
        response = self.client.get(reverse('client-priority-programs'), {'search': 'лечебное дело'})

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['code'], '31.05.01')
        self.assertEqual(response.data['results'][0]['service_fee_usd'], 5000)
