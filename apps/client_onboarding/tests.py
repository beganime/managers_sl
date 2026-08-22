from unittest.mock import patch
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.crm.models import Application, Client
from apps.education.models import City, Country, Program, University
from apps.organizations.models import Company
from users.models import User

from .models import (
    ClientProvisioningStep,
    ClientServiceIdentity,
    OnboardingReviewEvent,
    OnboardingSubmission,
)
from .services import build_service_credentials, split_person_name
from .tasks import disk_category_for_submission, notify_onboarding_status, provision_client_services


class PersonNameTests(SimpleTestCase):
    def test_standard_surname_name_patronymic_order(self):
        self.assertEqual(split_person_name('Иванов Александр Сергеевич'), ('Александр', 'Иванов'))

    def test_name_surname_order(self):
        self.assertEqual(split_person_name('Иван Иванов'), ('Иван', 'Иванов'))

    def test_credentials_use_given_name(self):
        submission = SimpleNamespace(full_name='Петрова Регина Ивановна')
        credentials = build_service_credentials(submission, 'SL-001')
        self.assertEqual(credentials['mobile_password'], 'Regina_0710')


class DiskCategoryTests(SimpleTestCase):
    def submission(self, funding_type='', payload=None):
        return SimpleNamespace(
            client=SimpleNamespace(funding_type=funding_type),
            payload=payload or {},
        )

    def test_master_has_priority_over_funding_type(self):
        submission = self.submission('budget', {'desired_education_level': 'Магистратура'})
        self.assertEqual(disk_category_for_submission(submission), 'Магистры')

    def test_funding_categories_and_contract_fallback(self):
        self.assertEqual(disk_category_for_submission(self.submission('government')), 'Гослиния')
        self.assertEqual(disk_category_for_submission(self.submission('budget')), 'Бюджет')
        self.assertEqual(disk_category_for_submission(self.submission('contract')), 'Контракт')
        self.assertEqual(disk_category_for_submission(self.submission()), 'Контракт')


class OnboardingApiTests(APITestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.manager = User.objects.create_user(
            email='manager@example.com',
            password='test-password',
            first_name='Manager',
            is_staff=True,
        )
        country = Country.objects.create(name='Россия', code='RU')
        city = City.objects.create(country=country, name='Казань')
        self.universities = []
        self.programs = []
        for index in range(1, 4):
            university = University.objects.create(
                company=self.company,
                country=country,
                city=city,
                name=f'ВУЗ {index}',
            )
            program = Program.objects.create(
                university=university,
                name=f'Программа {index}',
            )
            self.universities.append(university)
            self.programs.append(program)

    def applicant_payload(self):
        return {
            'kind': 'applicant',
            'academic_year': 2027,
            'full_name': 'Иван Иванов',
            'phone': '+99360000000',
            'email': 'ivan@example.com',
            'date_of_birth': '2008-01-01',
            'citizenship': 'Туркменистан',
            'payload': {'passport_number': 'TEST-001'},
            'fcm_token': 'test-fcm-token',
            'university_choices': [
                {
                    'university_id': university.id,
                    'program_ids': [program.id],
                }
                for university, program in zip(self.universities, self.programs)
            ],
        }

    def create_submission(self, payload=None):
        response = self.client.post(
            reverse('client-onboarding-create'),
            payload or self.applicant_payload(),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def express_payload(self, kind='applicant'):
        return {
            'kind': kind,
            'stage': 'express',
            'academic_year': 2027,
            'full_name': 'Иван Иванов' if kind == 'applicant' else 'Анна Школьница',
            'phone': '+99360000000',
            'email': 'client@example.com',
            'payload': {
                'requested_services': ['Консультация', 'Поступление под ключ'],
                'request_text': 'Хочу подобрать университет и подготовить документы.',
            },
        }

    def test_express_application_requires_valid_email_and_limits_comment(self):
        missing_email = self.express_payload()
        missing_email.pop('email')
        response = self.client.post(reverse('client-onboarding-create'), missing_email, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('email', response.data)

        invalid_email = self.express_payload()
        invalid_email['email'] = 'client.example.com'
        response = self.client.post(reverse('client-onboarding-create'), invalid_email, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('email', response.data)

        long_comment = self.express_payload()
        long_comment['payload']['request_text'] = 'а' * 1001
        response = self.client.post(reverse('client-onboarding-create'), long_comment, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('payload', response.data)

    def test_express_application_approval_creates_account_and_keeps_full_form_editable(self):
        created = self.create_submission(self.express_payload())
        submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
        self.client.force_authenticate(self.manager)
        approved = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        submission.refresh_from_db()
        self.assertEqual(submission.stage, 'express')
        self.assertEqual(submission.status, 'approved')
        self.assertIsNotNone(submission.client_id)
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(submission.client.sl_id, 'SL-001')
        self.assertEqual(submission.client.questionnaire.status, 'draft')

        self.client.force_authenticate(user=None)
        full_payload = self.applicant_payload()
        full_payload['stage'] = 'full'
        promoted = self.client.put(
            reverse('client-onboarding-detail', kwargs={'public_id': submission.public_id}),
            full_payload,
            format='json',
            HTTP_X_ONBOARDING_TOKEN=created.data['access_token'],
        )
        self.assertEqual(promoted.status_code, 200, promoted.data)
        submission.refresh_from_db()
        self.assertEqual(submission.stage, 'full')
        self.assertEqual(submission.status, 'submitted')

        self.client.force_authenticate(self.manager)
        approved_again = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(approved_again.status_code, 200, approved_again.data)
        submission.refresh_from_db()
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(submission.client.sl_id, 'SL-001')
        self.assertEqual(Application.objects.filter(client=submission.client).count(), 3)
        self.assertEqual(submission.client.questionnaire.status, 'approved')

    def test_full_post_cannot_duplicate_an_approved_express_client(self):
        created = self.create_submission(self.express_payload())
        submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
        self.client.force_authenticate(self.manager)
        approved = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        self.client.force_authenticate(user=None)
        duplicate = self.applicant_payload()
        duplicate.update({
            'stage': 'full',
            'email': self.express_payload()['email'],
            'phone': self.express_payload()['phone'],
        })
        response = self.client.post(reverse('client-onboarding-create'), duplicate, format='json')

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(OnboardingSubmission.objects.count(), 1)
        self.assertEqual(Client.objects.count(), 1)


    def test_anonymous_applicant_submission_requires_three_universities(self):
        payload = self.applicant_payload()
        payload['university_choices'] = payload['university_choices'][:2]

        response = self.client.post(reverse('client-onboarding-create'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(OnboardingSubmission.objects.count(), 0)

    def test_full_questionnaire_accepts_simple_university_and_program_text(self):
        payload = self.applicant_payload()
        payload['university_choices'] = []
        payload['payload'] = {
            **payload.get('payload', {}),
            'desired_universities': 'РУДН / Сеченова / БГМУ',
            'desired_program': 'лечебное дело и стоматология',
        }

        response = self.client.post(reverse('client-onboarding-create'), payload, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        submission = OnboardingSubmission.objects.get(public_id=response.data['public_id'])
        self.assertEqual(submission.university_choices.count(), 0)
        self.assertEqual(submission.payload['desired_universities'], 'РУДН / Сеченова / БГМУ')

    def test_status_requires_submission_token(self):
        created = self.create_submission()
        url = reverse('client-onboarding-detail', kwargs={'public_id': created.data['public_id']})

        denied = self.client.get(url)
        allowed = self.client.get(url, HTTP_X_ONBOARDING_TOKEN=created.data['access_token'])

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data['status'], 'submitted')

    @override_settings(
        STUDENTS_LIFE_PROVISION_API_URL='',
        STUDENTS_LIFE_PROVISION_TOKEN='',
        TMMAIL_PROVISION_API_URL='',
        TMMAIL_PROVISION_TOKEN='',
        DISK_PROVISION_API_URL='',
        DISK_PROVISION_SERVICE_TOKEN='',
    )
    def test_manager_approval_creates_client_questionnaire_and_one_application_per_university(self):
        created = self.create_submission()
        submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'approved')
        self.assertEqual(submission.client.sl_id, 'SL-001')
        self.assertEqual(submission.client.custom_data['mobile_password'], 'Ivan_0710')
        self.assertIsNone(submission.client.custom_data['tmmail_email'])
        self.assertEqual(submission.client.custom_data['tmmail_password'], 'Ivan_0710')
        self.assertEqual(submission.service_identity.shared_password, 'Ivan_0710')
        self.assertEqual(OnboardingReviewEvent.objects.filter(submission=submission, decision='approve').count(), 1)
        provisioning = provision_client_services.run(
            submission.client_id,
            str(submission.public_id),
        )
        self.assertEqual(provisioning['mobile'], 'disabled')
        self.assertEqual(provisioning['tmmail'], 'not_required')
        self.assertEqual(
            ClientProvisioningStep.objects.filter(
                submission=submission,
                status=ClientProvisioningStep.STATUS_DISABLED,
            ).count(),
            2,
        )
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(ClientServiceIdentity.objects.count(), 1)
        self.assertEqual(Application.objects.filter(client=submission.client).count(), 3)
        self.assertEqual(submission.client.questionnaire.status, 'approved')

        repeated = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(Client.objects.count(), 1)

    def test_client_can_resubmit_only_after_manager_requests_changes(self):
        created = self.create_submission()
        submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
        self.client.force_authenticate(self.manager)
        review = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'request_changes', 'comment': 'Исправьте номер паспорта.'},
            format='json',
        )
        self.assertEqual(review.status_code, 200)
        self.client.force_authenticate(user=None)

        payload = self.applicant_payload()
        payload['payload']['passport_number'] = 'TEST-002'
        response = self.client.put(
            reverse('client-onboarding-detail', kwargs={'public_id': submission.public_id}),
            payload,
            format='json',
            HTTP_X_ONBOARDING_TOKEN=created.data['access_token'],
        )

        self.assertEqual(response.status_code, 200, response.data)
        submission.refresh_from_db()
        self.assertEqual(submission.status, 'submitted')
        self.assertEqual(submission.payload['passport_number'], 'TEST-002')
        self.assertEqual(submission.review_comment, '')
        self.assertEqual(
            list(submission.review_events.values_list('decision', flat=True)),
            ['request_changes', 'resubmit'],
        )

    def test_manager_can_take_submission_into_review_before_approval(self):
        created = self.create_submission()
        submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
        self.client.force_authenticate(self.manager)

        started = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'start_review'},
            format='json',
        )
        approved = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )

        self.assertEqual(started.status_code, 200, started.data)
        self.assertEqual(started.data['status'], 'in_review')
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data['status'], 'approved')
        self.assertEqual(
            list(submission.review_events.values_list('decision', flat=True)),
            ['start_review', 'approve'],
        )

    def test_sl_id_is_global_while_mail_rollout_is_deferred(self):
        first = self.create_submission()
        second_payload = self.applicant_payload()
        second_payload['academic_year'] = 2028
        second_payload['phone'] = '+99360000001'
        second_payload['email'] = 'ivan-2@example.com'
        second = self.create_submission(second_payload)
        self.client.force_authenticate(self.manager)

        for created in (first, second):
            submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
            response = self.client.post(
                reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
                {'decision': 'approve'},
                format='json',
            )
            self.assertEqual(response.status_code, 200, response.data)

        clients = list(Client.objects.order_by('sl_id'))
        self.assertEqual([client.sl_id for client in clients], ['SL-001', 'SL-002'])
        self.assertIsNone(clients[0].custom_data['tmmail_email'])
        self.assertIsNone(clients[1].custom_data['tmmail_email'])

    @override_settings(
        STUDENTS_LIFE_PROVISION_API_URL='https://student.test/provision',
        STUDENTS_LIFE_PROVISION_TOKEN='student-token',
        SMTP_SL_API_BASE_URL='https://smtp.test',
        SMTP_SL_SERVICE_TOKEN='smtp-token',
        DISK_PROVISION_API_URL='https://disk.test/internal/folders',
        DISK_PROVISION_SERVICE_TOKEN='disk-token',
    )
    @patch('apps.client_onboarding.tasks.post_service', return_value={'status': 'created'})
    def test_successful_service_provisioning_is_not_repeated(self, post_service_mock):
        created = self.create_submission()
        submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
        self.client.force_authenticate(self.manager)
        approved = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        submission.refresh_from_db()

        first = provision_client_services.run(submission.client_id, str(submission.public_id))
        second = provision_client_services.run(submission.client_id, str(submission.public_id))

        self.assertEqual(first, {
            'mobile': 'success',
            'tmmail': 'not_required',
            'disk': 'success',
            'updated_at': first['updated_at'],
        })
        self.assertEqual(second['mobile'], 'success')
        self.assertEqual(second['tmmail'], 'not_required')
        self.assertEqual(second['disk'], 'success')
        self.assertEqual(post_service_mock.call_count, 2)
        self.assertEqual(
            list(
                submission.provisioning_steps.order_by('step')
                .values_list('attempt_count', flat=True)
            ),
            [1, 1, 0],
        )

    def test_school_submission_does_not_require_university_choices(self):
        response = self.create_submission({
            'kind': 'school_student',
            'stage': 'express',
            'academic_year': 2027,
            'full_name': 'Анна Школьница',
            'phone': '+99361111111',
            'email': 'school.student@example.com',
            'payload': {
                'school': 'Школа 1',
                'requested_services': ['Консультация'],
                'request_text': 'Хочу подготовиться к поступлению заранее.',
            },
        })

        submission = OnboardingSubmission.objects.get(public_id=response.data['public_id'])
        self.client.force_authenticate(self.manager)
        approved = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )

        self.assertEqual(approved.status_code, 200, approved.data)
        submission.refresh_from_db()
        self.assertEqual(submission.client.sl_id, 'SL-SCHOOL-2027-001')

    @patch('apps.client_onboarding.tasks.post_service', return_value={'status': 'sent', 'active_tokens': 1})
    def test_approved_submission_notifies_through_students_life_account(self, post_service_mock):
        created = self.create_submission()
        submission = OnboardingSubmission.objects.get(public_id=created.data['public_id'])
        self.client.force_authenticate(self.manager)
        approved = self.client.post(
            reverse('manager-onboarding-submission-review', kwargs={'pk': submission.pk}),
            {'decision': 'approve'},
            format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        result = notify_onboarding_status.run(submission.pk)

        self.assertEqual(result['status'], 'sent')
        post_service_mock.assert_called_once()
        self.assertEqual(post_service_mock.call_args.args[2]['sl_id'], 'SL-001')
