from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone


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
