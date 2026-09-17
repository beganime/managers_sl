from datetime import datetime, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.employees.models import EmployeeProfile, EmployeeRole
from apps.erp_notifications.models import NotificationTemplate
from apps.erp_notifications.tasks import auto_close_workdays, send_attendance_reminders
from apps.organizations.models import Company

from .models import AttendanceReminder, WorkDay


@override_settings(ATTENDANCE_WORKDAYS=(0, 1, 2, 3, 4, 5, 6), ATTENDANCE_ACTIVITY_PROTECTION_HOUR=17)
class WorkdayClosingPolicyTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.role = EmployeeRole.objects.create(code='manager', name='Менеджер', role_type='manager')

    def create_employee(self, email):
        user = get_user_model().objects.create_user(email=email, password='test-password')
        EmployeeProfile.objects.create(user=user, company=self.company, role=self.role)
        return user

    def set_activity(self, user, hour, minute=0):
        local_value = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(hour, minute)),
            timezone.get_current_timezone(),
        )
        type(user).objects.filter(pk=user.pk).update(last_activity=local_value)

    @patch('apps.erp_notifications.tasks.create_notification')
    def test_employee_without_start_is_recorded_as_missed(self, _create_notification):
        user = self.create_employee('absent@example.com')

        result = auto_close_workdays()

        workday = WorkDay.objects.get(employee=user, date=timezone.localdate())
        self.assertEqual(workday.status, WorkDay.STATUS_MISSED)
        self.assertEqual(result['missed'], 1)

    @patch('apps.erp_notifications.tasks.create_notification')
    def test_inactive_started_day_is_closed_at_18(self, _create_notification):
        user = self.create_employee('inactive@example.com')
        self.set_activity(user, 16, 59)
        workday = WorkDay.objects.create(
            company=self.company,
            employee=user,
            date=timezone.localdate(),
            status=WorkDay.STATUS_STARTED,
            started_at=timezone.now(),
        )

        result = auto_close_workdays()

        workday.refresh_from_db()
        self.assertEqual(workday.status, WorkDay.STATUS_AUTO_CLOSED)
        self.assertEqual(result['closed'], 1)

    @patch('apps.erp_notifications.tasks.create_notification')
    def test_evening_activity_requires_manual_close(self, _create_notification):
        user = self.create_employee('active@example.com')
        self.set_activity(user, 17, 30)
        workday = WorkDay.objects.create(
            company=self.company,
            employee=user,
            date=timezone.localdate(),
            status=WorkDay.STATUS_STARTED,
            started_at=timezone.now(),
        )

        result = auto_close_workdays()

        workday.refresh_from_db()
        self.assertEqual(workday.status, WorkDay.STATUS_STARTED)
        self.assertTrue(workday.requires_manual_close)
        self.assertEqual(result['waiting_manual_close'], 1)

    @patch('apps.erp_notifications.tasks.ensure_default_attendance_reminders')
    @patch('apps.erp_notifications.tasks.create_notification')
    def test_start_push_targets_every_active_employee(self, create_notification, _ensure_defaults):
        first = self.create_employee('first@example.com')
        second = self.create_employee('second@example.com')
        now = timezone.localtime()
        AttendanceReminder.objects.create(
            company=self.company,
            reminder_type=AttendanceReminder.REMINDER_START,
            scheduled_time=now.time().replace(second=0, microsecond=0),
            weekdays=[now.weekday()],
            message='Начните рабочий день.',
        )

        created = send_attendance_reminders(AttendanceReminder.REMINDER_START)

        self.assertEqual(created, 2)
        self.assertEqual({call.args[0] for call in create_notification.call_args_list}, {first, second})
        self.assertTrue(
            all(call.kwargs['channel'] == NotificationTemplate.CHANNEL_PUSH for call in create_notification.call_args_list)
        )
