from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from apps.organizations.models import Company
from apps.education.models import Country, University, Program
from .models import Client, Application
from .serializers import ClientSerializer, ApplicationSerializer
from .identity_reconciliation import reconcile_students, reconcile_applications


class IdentityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='synthetic-manager')
        self.company = Company.objects.create(name='Synthetic company')
        self.client_record = Client.objects.create(company=self.company, manager=self.user, full_name='Synthetic Student', phone='', public_id=None)
        self.country = Country.objects.create(name='Synthetic Country')
        self.university = University.objects.create(name='Synthetic University', abbreviation='SYN', country=self.country)
        self.program = Program.objects.create(name='Synthetic Program', university=self.university)
        self.application = Application.objects.create(client=self.client_record, company=self.company, manager=self.user,
            university_name='SYN', program_name=self.program.name, country=self.country.name, public_id=None)

    def test_dry_run_changes_nothing(self):
        report = reconcile_students(eligible_ids=[self.client_record.pk])
        self.assertEqual(report['before'], report['after'])
        self.client_record.refresh_from_db()
        self.assertIsNone(self.client_record.public_id)
        self.assertIsNone(self.client_record.sl_id)

    def test_apply_is_idempotent_and_keeps_existing_id(self):
        self.client_record.sl_id = 'SL-008'
        self.client_record.save(update_fields=['sl_id'])
        reconcile_students(apply=True, eligible_ids=[self.client_record.pk])
        self.client_record.refresh_from_db()
        self.assertEqual(self.client_record.sl_id, 'SL-008')
        self.assertIsNotNone(self.client_record.public_id)
        self.assertEqual(reconcile_students(apply=True, eligible_ids=[self.client_record.pk])['actions'], [])

    def test_missing_sl_requires_explicit_eligibility(self):
        reconcile_students(apply=True)
        self.client_record.refresh_from_db()
        self.assertIsNone(self.client_record.sl_id)
        reconcile_students(apply=True, eligible_ids=[self.client_record.pk])
        self.client_record.refresh_from_db()
        self.assertEqual(self.client_record.sl_id, 'SL-001')

    def test_shared_contact_blocks_sl_assignment_without_leaking_contact(self):
        self.client_record.email = 'synthetic@example.invalid'
        self.client_record.save(update_fields=['email'])
        Client.objects.create(company=self.company, manager=self.user, full_name='Other synthetic', phone='', email=self.client_record.email)
        report = reconcile_students(apply=True, eligible_ids=[self.client_record.pk])
        self.assertTrue(report['conflicts'])
        self.assertNotIn('synthetic@example.invalid', str(report))
        self.client_record.refresh_from_db()
        self.assertIsNone(self.client_record.sl_id)

    def test_unknown_eligibility_rolls_back(self):
        with self.assertRaises(ValueError):
            reconcile_students(apply=True, eligible_ids=[999999])
        self.client_record.refresh_from_db()
        self.assertIsNone(self.client_record.public_id)

    def test_command_default_is_dry_run(self):
        output = StringIO()
        call_command('backfill_student_identity', stdout=output)
        self.assertIn('dry-run', output.getvalue())
        self.client_record.refresh_from_db()
        self.assertIsNone(self.client_record.public_id)

    def test_exact_catalog_match_is_idempotent(self):
        reconcile_applications(apply=True)
        self.application.refresh_from_db()
        self.assertEqual(self.application.program, self.program)
        self.assertEqual(self.application.university, self.university)
        self.assertEqual(self.application.country, self.country.name)
        self.assertEqual(reconcile_applications(apply=True)['actions'], [])

    def test_multiple_program_matches_are_not_guessed(self):
        Program.objects.create(name=self.program.name, university=self.university, degree='master')
        self.assertTrue(reconcile_applications(apply=True)['conflicts'])
        self.application.refresh_from_db()
        self.assertIsNone(self.application.program_id)

    def test_other_company_catalog_is_not_used(self):
        self.university.company = Company.objects.create(name='Different company')
        self.university.save()
        self.assertTrue(reconcile_applications(apply=True)['conflicts'])
        self.application.refresh_from_db()
        self.assertIsNone(self.application.university_id)

    def test_new_identity_is_unique_and_api_read_only(self):
        other = Client.objects.create(company=self.company, manager=self.user, full_name='Another synthetic', phone='')
        self.assertIsNotNone(other.public_id)
        self.assertTrue(ClientSerializer().fields['public_id'].read_only)
        for name in ('public_id', 'university', 'program', 'country_reference', 'academic_year'):
            self.assertTrue(ApplicationSerializer().fields[name].read_only)


class IdentityMigrationTests(TransactionTestCase):
    def test_expansion_preserves_existing_rows_and_never_reuses_one_uuid(self):
        executor = MigrationExecutor(connection)
        old = [('crm', '0014_alter_client_funding_type')]
        new = [('crm', '0015_canonical_identity_expand')]
        executor.migrate(old)
        try:
            state = executor.loader.project_state(old).apps
            user = state.get_model('auth', 'User').objects.create(username='migration-synthetic')
            company = state.get_model('organizations', 'Company').objects.create(name='Migration synthetic')
            legacy = state.get_model('crm', 'Client')
            first = legacy.objects.create(company_id=company.pk, manager_id=user.pk, full_name='First synthetic', phone='', sl_id='SL-123')
            second = legacy.objects.create(company_id=company.pk, manager_id=user.pk, full_name='Second synthetic', phone='')
            MigrationExecutor(connection).migrate(new)
            self.assertEqual(Client.objects.filter(public_id=None).count(), 2)
            self.assertEqual(Client.objects.get(pk=first.pk).sl_id, 'SL-123')
            reconcile_students(apply=True)
            self.assertNotEqual(Client.objects.get(pk=first.pk).public_id, Client.objects.get(pk=second.pk).public_id)
            self.assertEqual(Client.objects.count(), 2)
        finally:
            MigrationExecutor(connection).migrate(new)
