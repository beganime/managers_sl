from datetime import date

from django.test import TestCase

from apps.client_onboarding.models import OnboardingSubmission, OnboardingUniversityChoice
from apps.client_onboarding.services import approve_submission
from apps.education.models import City, Country, Program, University
from apps.organizations.models import Company
from users.models import User

from .client import column_letter, quote_sheet
from .models import SheetRowBinding
from .schema import EXAM_HEADERS, safe_sheet_title, university_acronym
from .services import sync_reference_data, sync_submission


class FakeSheetsGateway:
    spreadsheet_id = 'test-book'

    def __init__(self):
        self.rows = {}
        self.reference_columns = {}
        self.known_titles = {'Общее', 'Справочники'}

    def sheet_titles(self):
        return set(self.known_titles)

    def ensure_sheet(self, sheet_name, headers):
        self.known_titles.add(sheet_name)
        self.rows.setdefault(sheet_name, {})

    def upsert_row(
        self,
        sheet_name,
        identity_header,
        identity_value,
        values,
        create_only_values=None,
    ):
        sheet_rows = self.rows.setdefault(sheet_name, {})
        created = identity_value not in sheet_rows
        if created:
            sheet_rows[identity_value] = dict(create_only_values or {})
        sheet_rows.setdefault(identity_value, {}).update(values)
        return list(sheet_rows).index(identity_value) + 2, created

    def replace_reference_column(self, sheet_name, column, header, values):
        self.reference_columns[column] = (header, list(values))
        return len(values)


class SchemaTests(TestCase):
    def test_exam_contract_matches_current_google_sheet(self):
        self.assertEqual(
            EXAM_HEADERS,
            (
                'ID экзамена', 'Айди', 'Внутренний ID', 'Вуз', 'Направление',
                'Экзамен', 'Дата и время', 'логин', 'Пароль', 'почта',
                'Место или ссылка', 'Ответственный', 'Обновлено', 'Версия уведомления',
            ),
        )

    def test_sheet_helpers(self):
        self.assertEqual(column_letter(0), 'A')
        self.assertEqual(column_letter(26), 'AA')
        self.assertEqual(quote_sheet("КФУ 'Тест'"), "'КФУ ''Тест'''" )
        self.assertEqual(safe_sheet_title('КФУ/тест'), 'КФУ тест')
        self.assertEqual(university_acronym('Казанский федеральный университет'), 'КФУ')


class SheetsSyncServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.manager = User.objects.create_user(
            email='manager-sheets@example.com',
            password='test-password',
            first_name='Анна',
            last_name='Менеджер',
            role='manager',
        )
        country = Country.objects.create(name='Россия', code='RU')
        city = City.objects.create(country=country, name='Казань')
        self.choices = []
        for index in range(1, 4):
            university = University.objects.create(
                company=self.company,
                country=country,
                city=city,
                name=f'Тестовый университет {index}',
            )
            program = Program.objects.create(
                university=university,
                name=f'Программа {index}',
            )
            self.choices.append((university, program))

    def create_approved_submission(self):
        submission = OnboardingSubmission.objects.create(
            access_token_hash='test',
            kind=OnboardingSubmission.KIND_APPLICANT,
            academic_year=2027,
            full_name='Иван Иванов',
            phone='+99360000000',
            email='ivan@example.com',
            date_of_birth=date(2008, 7, 10),
            citizenship='Туркменистан',
            payload={'passport_number': 'TEST-001', 'funding_type': 'гос'},
        )
        for rank, (university, program) in enumerate(self.choices, start=1):
            choice = OnboardingUniversityChoice.objects.create(
                submission=submission,
                university=university,
                rank=rank,
            )
            choice.programs.add(program)
        return approve_submission(submission, self.manager)

    def test_approved_submission_is_upserted_without_duplicate_rows(self):
        submission = self.create_approved_submission()
        gateway = FakeSheetsGateway()

        first = sync_submission(submission.pk, gateway=gateway)
        second = sync_submission(submission.pk, gateway=gateway)

        self.assertEqual(submission.client.sl_id, 'SL-001')
        self.assertEqual(first['processed'], 4)
        self.assertEqual(second['processed'], 4)
        self.assertEqual(gateway.rows['Общее']['SL-001']['ФИО абитуриента'], 'Иван Иванов')
        self.assertEqual(len(gateway.rows['Общее']), 1)
        self.assertEqual(SheetRowBinding.objects.filter(sl_id='SL-001').count(), 4)

        gateway.rows['Общее']['SL-001']['Статус сейчас'] = 'Ручной статус'
        sync_submission(submission.pk, gateway=gateway)
        self.assertEqual(gateway.rows['Общее']['SL-001']['Статус сейчас'], 'Ручной статус')

    def test_reference_sync_reads_existing_catalogs_without_modifying_them(self):
        gateway = FakeSheetsGateway()

        result = sync_reference_data(gateway=gateway)

        self.assertEqual(result['status'], 'success')
        self.assertIn('Анна Менеджер', gateway.reference_columns['A'][1])
        self.assertIn('Казань', gateway.reference_columns['B'][1])
        self.assertEqual(len(gateway.reference_columns['K'][1]), 3)
        self.assertEqual(len(gateway.reference_columns['L'][1]), 3)
