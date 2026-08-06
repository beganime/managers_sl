from django.urls import reverse
from rest_framework.test import APITestCase

from apps.crm.models import Application, Client
from apps.education.models import City, Country, Program, University
from apps.organizations.models import Company
from users.models import User

from .models import OnboardingSubmission
from .tasks import provision_client_services


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

    def test_anonymous_applicant_submission_requires_three_universities(self):
        payload = self.applicant_payload()
        payload['university_choices'] = payload['university_choices'][:2]

        response = self.client.post(reverse('client-onboarding-create'), payload, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(OnboardingSubmission.objects.count(), 0)

    def test_status_requires_submission_token(self):
        created = self.create_submission()
        url = reverse('client-onboarding-detail', kwargs={'public_id': created.data['public_id']})

        denied = self.client.get(url)
        allowed = self.client.get(url, HTTP_X_ONBOARDING_TOKEN=created.data['access_token'])

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data['status'], 'submitted')

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
        self.assertEqual(submission.client.sl_id, 'SL-2027-001')
        self.assertEqual(submission.client.custom_data['mobile_password'], 'Ivan_0710')
        self.assertEqual(submission.client.custom_data['tmmail_email'], 'ivan.ivanov2008@tmmail.ru')
        provisioning = provision_client_services.run(
            submission.client_id,
            str(submission.public_id),
        )
        self.assertEqual(provisioning['mobile'], 'disabled')
        self.assertEqual(provisioning['tmmail'], 'disabled')
        self.assertEqual(Client.objects.count(), 1)
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

    def test_school_submission_does_not_require_university_choices(self):
        response = self.create_submission({
            'kind': 'school_student',
            'academic_year': 2027,
            'full_name': 'Анна Школьница',
            'phone': '+99361111111',
            'payload': {'school': 'Школа 1'},
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
