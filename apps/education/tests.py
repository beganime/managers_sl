import json
from decimal import Decimal

from django.test import TestCase

from .importers import import_programs_from_json
from .models import City, Country, Currency, Program, ProgramFee, University


class ProgramJsonImportTests(TestCase):
    def setUp(self):
        self.currency = Currency.objects.create(
            code='USD',
            name='US Dollar',
            symbol='$',
            rate_to_usd=Decimal('1.000000'),
        )
        self.country = Country.objects.create(name='Россия', code='RU')
        self.city = City.objects.create(country=self.country, name='Астрахань')
        self.university = University.objects.create(
            country=self.country,
            city=self.city,
            local_currency=self.currency,
            name='АГУ (Астраханский государственный университет)',
        )

    def payload(self, **overrides):
        data = {
            'university': self.university.name,
            'name': 'Информационная безопасность',
            'degree': 'bachelor',
            'tuition_fee': 163600.0,
            'service_fee': 500.0,
            'duration': '4 года',
            'is_active': True,
        }
        data.update(overrides)
        return data

    def test_import_valid_json_array(self):
        content = json.dumps([self.payload()], ensure_ascii=False).encode('utf-8')

        result = import_programs_from_json(content, dry_run=False, update_existing=True)

        self.assertEqual(result.total_rows, 1)
        self.assertEqual(result.created, 1)
        self.assertFalse(result.errors)
        program = Program.objects.get(name='Информационная безопасность')
        self.assertEqual(program.university, self.university)
        fee = program.fees.get()
        self.assertEqual(fee.tuition_fee, Decimal('163600.00'))
        self.assertEqual(fee.service_fee_usd, Decimal('500.00'))

    def test_import_json_objects_without_outer_array(self):
        first = json.dumps(self.payload(name='Архитектура'), ensure_ascii=False)
        second = json.dumps(self.payload(name='Дизайн', tuition_fee=282100), ensure_ascii=False)
        content = f'{first},\n{second}'.encode('utf-8')

        result = import_programs_from_json(content, dry_run=False, update_existing=True)

        self.assertEqual(result.total_rows, 2)
        self.assertEqual(result.created, 2)
        self.assertEqual(Program.objects.count(), 2)

    def test_unknown_university_returns_error(self):
        content = json.dumps([self.payload(university='Неизвестный ВУЗ')], ensure_ascii=False).encode('utf-8')

        result = import_programs_from_json(content, dry_run=False, update_existing=True)

        self.assertEqual(result.created, 0)
        self.assertEqual(result.skipped, 1)
        self.assertIn('Университет не найден', result.errors[0].message)

    def test_update_existing_program(self):
        program = Program.objects.create(
            university=self.university,
            name='Информационная безопасность',
            degree='bachelor',
            duration='4 года',
            is_active=True,
        )
        ProgramFee.objects.create(
            program=program,
            currency=self.currency,
            tuition_fee=Decimal('100.00'),
            service_fee_usd=Decimal('10.00'),
        )
        content = json.dumps([self.payload(tuition_fee=200000, service_fee=750, is_active='нет')], ensure_ascii=False).encode('utf-8')

        result = import_programs_from_json(content, dry_run=False, update_existing=True)

        self.assertEqual(result.updated, 1)
        self.assertEqual(Program.objects.count(), 1)
        program.refresh_from_db()
        self.assertFalse(program.is_active)
        fee = program.fees.get()
        self.assertEqual(fee.tuition_fee, Decimal('200000.00'))
        self.assertEqual(fee.service_fee_usd, Decimal('750.00'))

    def test_dry_run_does_not_create_records(self):
        content = json.dumps([self.payload()], ensure_ascii=False).encode('utf-8')

        result = import_programs_from_json(content, dry_run=True, update_existing=True)

        self.assertEqual(result.created, 1)
        self.assertEqual(Program.objects.count(), 0)

    def test_invalid_degree_returns_error(self):
        content = json.dumps([self.payload(degree='магия')], ensure_ascii=False).encode('utf-8')

        result = import_programs_from_json(content, dry_run=False, update_existing=True)

        self.assertEqual(result.created, 0)
        self.assertEqual(result.skipped, 1)
        self.assertIn('Неподдерживаемая степень', result.errors[0].message)
