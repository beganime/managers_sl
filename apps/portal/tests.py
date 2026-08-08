from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.client_onboarding.models import OnboardingReviewEvent, OnboardingSubmission


class DashboardBirthdayGreetingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='birthday@example.com',
            password='test-password',
            first_name='Анна',
            is_staff=True,
        )
        self.client.force_login(self.user)

    def test_greeting_is_shown_on_users_birthday(self):
        today = timezone.localdate()
        self.user.dob = today.replace(year=today.year - 25)
        self.user.save(update_fields=['dob'])

        response = self.client.get(reverse('portal:dashboard'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'С днём рождения, Анна!')
        self.assertContains(response, 'Спасибо, что вы с нами.')

    def test_greeting_is_hidden_on_other_days(self):
        another_day = timezone.localdate() - timedelta(days=1)
        self.user.dob = another_day.replace(year=another_day.year - 25)
        self.user.save(update_fields=['dob'])

        response = self.client.get(reverse('portal:dashboard'), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'С днём рождения, Анна!')


class PortalOnboardingWorkflowTests(TestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(
            email='onboarding-manager@example.com',
            password='test-password',
            first_name='Мария',
            is_staff=True,
        )
        self.submission = OnboardingSubmission.objects.create(
            access_token_hash='test-token-hash',
            kind=OnboardingSubmission.KIND_SCHOOL_STUDENT,
            academic_year=2027,
            full_name='Тестовый Школьник',
            phone='+99361111111',
            payload={'school': 'Школа 1', 'school_class': '10'},
        )
        self.client.force_login(self.manager)

    def test_manager_can_open_incoming_submission(self):
        listing = self.client.get(reverse('portal:onboarding_submissions'), secure=True)
        detail = self.client.get(
            reverse('portal:onboarding_submission_detail', args=[self.submission.pk]),
            secure=True,
        )

        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Тестовый Школьник')
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Школа 1')
        self.assertContains(detail, 'Взять на проверку')

    def test_manager_can_take_submission_into_review_from_portal(self):
        response = self.client.post(
            reverse('portal:onboarding_submission_review', args=[self.submission.pk]),
            {'decision': 'start_review'},
            secure=True,
        )

        self.assertRedirects(
            response,
            reverse('portal:onboarding_submission_detail', args=[self.submission.pk]),
            fetch_redirect_response=False,
        )
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, OnboardingSubmission.STATUS_IN_REVIEW)
        self.assertEqual(self.submission.reviewed_by, self.manager)
        self.assertTrue(
            OnboardingReviewEvent.objects.filter(
                submission=self.submission,
                decision=OnboardingReviewEvent.DECISION_START_REVIEW,
            ).exists()
        )
