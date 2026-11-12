from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.employees.models import EmployeeProfile, EmployeeRole
from apps.organizations.models import Company

from . import bot_commands
from .models import EmployeeTelegramAccount, WorkDay


@override_settings(ATTENDANCE_WORKDAYS=(0, 1, 2, 3, 4, 5, 6))
class BotCommandsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.role = EmployeeRole.objects.create(code='manager', name='Менеджер', role_type='manager')
        self.user = get_user_model().objects.create_user(email='bot@example.com', password='test-password')
        EmployeeProfile.objects.create(user=self.user, company=self.company, role=self.role)
        self.account = EmployeeTelegramAccount.objects.create(
            employee=self.user,
            telegram_user_id=4242,
            chat_id=4242,
        )

    def test_keyboard_shows_only_start_when_day_not_started(self):
        workday = bot_commands.get_today_workday(self.user)
        keyboard = bot_commands.build_keyboard(workday, self.user)
        texts = [btn['text'] for row in keyboard['inline_keyboard'] for btn in row]
        self.assertIn(bot_commands.BUTTON_START, texts)
        self.assertNotIn(bot_commands.BUTTON_CLOSE, texts)
        self.assertNotIn(bot_commands.BUTTON_REPORT, texts)

    def test_start_opens_workday_and_unlocks_close(self):
        text, keyboard = bot_commands.action_start(self.user)
        workday = WorkDay.objects.get(employee=self.user, date=timezone.localdate())
        self.assertEqual(workday.status, WorkDay.STATUS_STARTED)
        self.assertIn('начат', text.lower())
        texts = [btn['text'] for row in keyboard['inline_keyboard'] for btn in row]
        self.assertIn(bot_commands.BUTTON_CLOSE, texts)
        self.assertNotIn(bot_commands.BUTTON_START, texts)

    def test_double_start_is_idempotent(self):
        bot_commands.action_start(self.user)
        text, _ = bot_commands.action_start(self.user)
        self.assertIn('уже идёт', text)

    def test_close_before_start_is_rejected(self):
        text, keyboard = bot_commands.action_close(self.user)
        self.assertIn('ещё не начат', text)
        workday = WorkDay.objects.get(employee=self.user, date=timezone.localdate())
        self.assertEqual(workday.status, WorkDay.STATUS_NOT_STARTED)
        texts = [btn['text'] for row in keyboard['inline_keyboard'] for btn in row]
        self.assertIn(bot_commands.BUTTON_START, texts)

    def test_report_flow_via_text(self):
        bot_commands.action_start(self.user)
        prompt, _ = bot_commands.handle_private_text(self.account, bot_commands.BUTTON_REPORT)
        self.assertIn('отчёт', prompt.lower())
        reply, keyboard = bot_commands.handle_private_text(self.account, 'Обработала 5 заявок, созвон с вузом.')
        self.assertIn('Отчёт отправлен', reply)
        workday = WorkDay.objects.get(employee=self.user, date=timezone.localdate())
        self.assertTrue(workday.has_report)
        self.assertEqual(workday.daily_report.content, 'Обработала 5 заявок, созвон с вузом.')
        # After the report the keyboard still offers close.
        texts = [btn['text'] for row in keyboard['inline_keyboard'] for btn in row]
        self.assertIn(bot_commands.BUTTON_CLOSE, texts)

    def test_report_text_without_prompt_shows_help(self):
        reply, keyboard = bot_commands.handle_private_text(self.account, 'случайное сообщение')
        self.assertIn('Управляйте рабочим днем', reply)

    def test_close_after_start_closes_day(self):
        bot_commands.action_start(self.user)
        text, keyboard = bot_commands.action_close(self.user)
        workday = WorkDay.objects.get(employee=self.user, date=timezone.localdate())
        self.assertIn(workday.status, {WorkDay.STATUS_CLOSED, WorkDay.STATUS_AUTO_CLOSED})
        self.assertIn('закрыт', text.lower())
        texts = [btn['text'] for row in keyboard['inline_keyboard'] for btn in row]
        self.assertIn(bot_commands.BUTTON_START, texts)

    def test_stats_lists_week_days(self):
        bot_commands.action_start(self.user)
        bot_commands.handle_private_text(self.account, bot_commands.BUTTON_REPORT)
        bot_commands.handle_private_text(self.account, 'Итоги дня.')
        text, _ = bot_commands.action_stats(self.user)
        self.assertIn('Статистика', text)
        self.assertIn('Всего за неделю', text)

    def test_callback_dispatch(self):
        text, keyboard = bot_commands.handle_callback(self.account, bot_commands.CALLBACK_START)
        self.assertIn('начат', text.lower())
        text, _ = bot_commands.handle_callback(self.account, 'att:unknown')
        self.assertIn('Неизвестная команда', text)

    def test_final_day_cannot_restart(self):
        bot_commands.action_start(self.user)
        bot_commands.action_close(self.user)
        text, _ = bot_commands.action_start(self.user)
        self.assertIn('уже завершён', text)

    def test_binding_reply_contains_keyboard(self):
        text, keyboard = bot_commands.binding_success_reply(self.user)
        self.assertIn('подключён', text)
        self.assertTrue(keyboard['inline_keyboard'])

    def test_admin_sees_team_button_and_roster(self):
        admin_role = EmployeeRole.objects.create(code='00003', name='Администрация', role_type='admin')
        admin_user = get_user_model().objects.create_user(email='boss@example.com', password='x', is_staff=True)
        EmployeeProfile.objects.create(user=admin_user, company=self.company, role=admin_role)
        admin_account = EmployeeTelegramAccount.objects.create(employee=admin_user, telegram_user_id=777, chat_id=777)

        text, keyboard = bot_commands.handle_callback(admin_account, bot_commands.CALLBACK_TEAM)
        self.assertIn('Кто на работе', text)
        texts = [btn['text'] for row in keyboard['inline_keyboard'] for btn in row]
        self.assertIn(bot_commands.BUTTON_TEAM, texts)

        # Non-admin is rejected.
        text, _ = bot_commands.handle_callback(self.account, bot_commands.CALLBACK_TEAM)
        self.assertIn('только администраторам', text)

    def test_team_roster_marks_started_employee(self):
        bot_commands.action_start(self.user)
        admin_role = EmployeeRole.objects.create(code='00003', name='Администрация', role_type='admin')
        admin_user = get_user_model().objects.create_user(email='boss2@example.com', password='x', is_staff=True)
        EmployeeProfile.objects.create(user=admin_user, company=self.company, role=admin_role)
        text = bot_commands.team_overview_text(self.company)
        self.assertIn('Кто на работе', text)
        self.assertIn('🟢', text)

    def test_admin_daily_digest_creates_delivery(self):
        from .telegram import register_admin_daily_digest

        admin_role = EmployeeRole.objects.create(code='00003', name='Администрация', role_type='admin')
        admin_user = get_user_model().objects.create_user(email='boss3@example.com', password='x', is_staff=True)
        EmployeeProfile.objects.create(user=admin_user, company=self.company, role=admin_role)
        EmployeeTelegramAccount.objects.create(employee=admin_user, telegram_user_id=778, chat_id=778)

        created = register_admin_daily_digest()
        self.assertEqual(created, 1)
        self.assertEqual(register_admin_daily_digest(), 0)  # deduplicated per day
