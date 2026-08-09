from datetime import date

from django.test import TestCase

from apps.client_onboarding.models import OnboardingSubmission, OnboardingUniversityChoice
from apps.client_onboarding.serializers import PublicOnboardingStatusSerializer
from apps.client_onboarding.services import approve_submission
from apps.education.models import City, Country, Program, University
from apps.organizations.models import Company
from users.models import User

from .client import column_letter, quote_sheet
from .models import ClientAdmissionSnapshot, SheetRowBinding
from .schema import EXAM_HEADERS, safe_sheet_title, university_acronym
from .services import (
    import_onboarding_decisions,
    import_public_client_statuses,
    sync_onboarding_inbox,
    sync_onboarding_submission,
    sync_reference_data,
    sync_submission,
)


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

    def set_dropdown_validation(self, sheet_name, header, values, start_row=2, end_row=2000):
        return None

    def read_rows(self, sheet_name, start_row=2):
        return [
            {
                'row_number': index,
                'values': {'Айди': sl_id, **values},
            }
            for index, (sl_id, values) in enumerate(
                self.rows.get(sheet_name, {}).items(),
                start=start_row,
            )
        ]


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
        self.assertEqual(university_acronym('БГУ (Белорусский государственный университет)'), 'БГУ')


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
        submission = self.create_submitted_submission()
        return approve_submission(submission, self.manager)

    def create_submitted_submission(self):
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
        return submission

    def test_google_sheet_status_approves_submission_and_writes_general_row(self):
        submission = self.create_submitted_submission()
        gateway = FakeSheetsGateway()

        initial = sync_onboarding_submission(submission.pk, gateway=gateway)
        inbox_row = gateway.rows['Заявки из анкеты'][str(submission.public_id)]
        self.assertTrue(initial['created'])
        self.assertEqual(inbox_row['Статус'], 'Ожидание')

        inbox_row['Статус'] = 'Подтвержден'
        result = import_onboarding_decisions(gateway=gateway)

        submission.refresh_from_db()
        self.assertEqual(result, {'status': 'success', 'processed': 1, 'failed': 0})
        self.assertEqual(submission.status, OnboardingSubmission.STATUS_APPROVED)
        self.assertIsNotNone(submission.client_id)
        self.assertEqual(inbox_row['Статус'], 'Подтвержден')
        self.assertEqual(inbox_row['SL-ID'], submission.client.sl_id)
        self.assertIn('Обработано', inbox_row['Результат обработки'])
        self.assertEqual(
            gateway.rows['Общее'][submission.client.sl_id]['ФИО абитуриента'],
            'Иван Иванов',
        )

        repeated = import_onboarding_decisions(gateway=gateway)
        self.assertEqual(repeated, {'status': 'success', 'processed': 0, 'failed': 0})
        self.assertEqual(OnboardingSubmission.objects.filter(client__isnull=False).count(), 1)

    def test_inbox_recovery_does_not_overwrite_manager_status(self):
        submission = self.create_submitted_submission()
        gateway = FakeSheetsGateway()
        sync_onboarding_submission(submission.pk, gateway=gateway)
        inbox_row = gateway.rows['Заявки из анкеты'][str(submission.public_id)]
        inbox_row['Статус'] = 'Подтвержден'

        result = sync_onboarding_inbox(gateway=gateway)

        self.assertEqual(result, {'status': 'success', 'processed': 0, 'failed': 0})
        self.assertEqual(inbox_row['Статус'], 'Подтвержден')

    def test_approved_submission_is_upserted_without_duplicate_rows(self):
        submission = self.create_approved_submission()
        gateway = FakeSheetsGateway()

        first = sync_submission(submission.pk, gateway=gateway)
        second = sync_submission(submission.pk, gateway=gateway)

        self.assertEqual(submission.client.sl_id, 'SL-001')
        self.assertEqual(first['processed'], 1)
        self.assertEqual(second['processed'], 1)
        self.assertEqual(gateway.rows['Общее']['SL-001']['ФИО абитуриента'], 'Иван Иванов')
        self.assertEqual(len(gateway.rows['Общее']), 1)
        self.assertEqual(SheetRowBinding.objects.filter(sl_id='SL-001').count(), 1)

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

    def test_only_public_operational_fields_are_imported_for_client(self):
        submission = self.create_approved_submission()
        gateway = FakeSheetsGateway()
        sync_submission(submission.pk, gateway=gateway)
        row = gateway.rows['Общее']['SL-001']
        row.update({
            'Статус сейчас': 'Приглашение готово',
            'В какой город приглашение': 'Казань',
            'Встреча': 'Да',
            'Где находится сейчас': 'Ашгабад',
            'Номер паспорта': 'MUST-NOT-BE-IMPORTED',
            'Пароль': 'MUST-NOT-BE-IMPORTED',
            'Сколько оплатил': '2500',
            'Комментарий': 'Внутренняя заметка менеджера',
        })

        first = import_public_client_statuses(gateway=gateway)
        second = import_public_client_statuses(gateway=gateway)

        snapshot = ClientAdmissionSnapshot.objects.get(client=submission.client)
        self.assertEqual(first, {'status': 'success', 'processed': 1, 'failed': 0})
        self.assertEqual(second, {'status': 'success', 'processed': 0, 'failed': 0})
        self.assertEqual(snapshot.current_status, 'Приглашение готово')
        self.assertEqual(snapshot.invitation_city, 'Казань')
        self.assertEqual(snapshot.meeting, 'Да')
        self.assertEqual(snapshot.current_location, 'Ашгабад')
        serialized = PublicOnboardingStatusSerializer(submission).data
        self.assertEqual(serialized['admission_status']['current_status'], 'Приглашение готово')
        self.assertNotIn('passport', str(serialized).casefold())
        self.assertNotIn('MUST-NOT-BE-IMPORTED', str(serialized))
