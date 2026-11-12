"""Interactive Telegram bot commands for the personal attendance chat.

The bot answers inside the webhook response (no outbound Bot API call), so the
features work even while proactive delivery goes through the relay queue.
Commands: start workday, write daily report, close workday, week statistics.
"""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.core.permissions import get_employee_profile

from .models import EmployeeTelegramAccount, WorkDay
from .services import is_scheduled_workday, should_track_employee

BUTTON_START = '▶️ Начать рабочий день'
BUTTON_REPORT = '📝 Написать отчёт'
BUTTON_CLOSE = '⏹ Закрыть рабочий день'
BUTTON_STATS = '📊 Статистика'
BUTTON_TEAM = '👥 Кто на работе'

CALLBACK_START = 'att:start'
CALLBACK_REPORT = 'att:report'
CALLBACK_CLOSE = 'att:close'
CALLBACK_STATS = 'att:stats'
CALLBACK_TEAM = 'att:team'


def is_admin_user(user):
    if user.is_superuser or user.is_staff:
        return True
    profile = get_employee_profile(user)
    role = getattr(profile, 'role', None)
    return bool(role and str(getattr(role, 'code', '')) == '00003')

REPORT_AWAIT_KEY = 'attendance:bot:await-report:{employee_id}'
REPORT_AWAIT_TTL = 30 * 60  # seconds

HELP_TEXT = (
    'Управляйте рабочим днем прямо здесь — даже если сайт недоступен.\n'
    'Команды бота:\n'
    f'{BUTTON_START} — открыть рабочий день\n'
    f'{BUTTON_REPORT} — отправить ежедневный отчёт\n'
    f'{BUTTON_CLOSE} — закрыть рабочий день\n'
    f'{BUTTON_STATS} — статистика за неделю'
)


def resolve_account(telegram_user_id):
    return (
        EmployeeTelegramAccount.objects
        .filter(telegram_user_id=telegram_user_id, is_active=True)
        .select_related('employee')
        .first()
    )


def get_today_workday(user):
    today = timezone.localdate()
    employee = get_employee_profile(user)
    if not employee or not employee.company_id:
        return None
    workday, _ = WorkDay.objects.get_or_create(
        company=employee.company,
        employee=user,
        date=today,
        defaults={
            'office': employee.office,
            'status': WorkDay.STATUS_NOT_STARTED,
            'report_required': True,
        },
    )
    return workday


def workday_is_open(workday):
    return workday.status in {WorkDay.STATUS_STARTED, WorkDay.STATUS_REPORT_SUBMITTED}


def build_keyboard(workday, user=None):
    rows = []
    admin = bool(user is not None and is_admin_user(user))
    tracked = user is not None and should_track_employee(user)
    if workday is not None and workday_is_open(workday):
        rows.append([
            {'text': BUTTON_REPORT, 'callback_data': CALLBACK_REPORT},
            {'text': BUTTON_CLOSE, 'callback_data': CALLBACK_CLOSE},
        ])
    elif tracked:
        rows.append([{'text': BUTTON_START, 'callback_data': CALLBACK_START}])
    if admin:
        rows.append([{'text': BUTTON_TEAM, 'callback_data': CALLBACK_TEAM}])
    rows.append([{'text': BUTTON_STATS, 'callback_data': CALLBACK_STATS}])
    return {'inline_keyboard': rows}


def _status_error(user):
    if not should_track_employee(user):
        return 'Учёт рабочего дня для вас не включён. Обратитесь к администратору.'
    return None


def action_start(user):
    error = _status_error(user)
    if error:
        return error, None
    if not is_scheduled_workday(timezone.localdate()):
        return 'Сегодня нерабочий день — начинать рабочий день не нужно.', None
    workday = get_today_workday(user)
    if workday is None:
        return 'Не найден профиль сотрудника. Обратитесь к администратору.', None
    if workday_is_open(workday):
        started = timezone.localtime(workday.started_at).strftime('%H:%M') if workday.started_at else '—'
        return f'Рабочий день уже идёт (начат в {started}).', build_keyboard(workday, user)
    if workday.status in WorkDay.FINAL_STATUSES:
        return 'Сегодняшний рабочий день уже завершён. Новый день откроется завтра.', build_keyboard(workday, user)
    workday.start(note='Через Telegram-бота.')
    started = timezone.localtime(workday.started_at).strftime('%H:%M')
    return f'Рабочий день начат в {started}. Хорошей работы!', build_keyboard(workday, user)


def action_report(user):
    error = _status_error(user)
    if error:
        return error, None
    workday = get_today_workday(user)
    if workday is None:
        return 'Не найден профиль сотрудника. Обратитесь к администратору.', None
    if not workday_is_open(workday):
        return 'Сначала начните рабочий день — кнопка «Написать отчёт» станет доступна.', build_keyboard(workday, user)
    cache.set(REPORT_AWAIT_KEY.format(employee_id=user.pk), workday.pk, REPORT_AWAIT_TTL)
    return 'Напишите отчёт одним следующим сообщением: итоги дня, планы или проблемы. Отправлю его как ежедневный отчёт.', build_keyboard(workday, user)


def _submit_report_text(user, text):
    workday_id = cache.get(REPORT_AWAIT_KEY.format(employee_id=user.pk))
    if not workday_id:
        return None
    workday = WorkDay.objects.filter(pk=workday_id, employee=user).first()
    if not workday:
        cache.delete(REPORT_AWAIT_KEY.format(employee_id=user.pk))
        return 'Не удалось найти сегодняшний рабочий день. Попробуйте ещё раз.'
    content = ' '.join(str(text).split()).strip()
    if len(content) < 3:
        return 'Отчёт слишком короткий — напишите хотя бы пару слов.'
    workday.submit_report(content)
    cache.delete(REPORT_AWAIT_KEY.format(employee_id=user.pk))
    return 'Отчёт отправлен. Спасибо!'


def action_close(user):
    error = _status_error(user)
    if error:
        return error, None
    workday = get_today_workday(user)
    if workday is None:
        return 'Не найден профиль сотрудника. Обратитесь к администратору.', None
    if not workday_is_open(workday):
        return 'Рабочий день ещё не начат — кнопка «Закрыть рабочий день» станет доступна после начала дня.', build_keyboard(workday, user)
    workday.close(user=user, comment='Через Telegram-бота.')
    workday.refresh_from_db()
    hours = workday.total_work_hours
    return (
        f'Рабочий день закрыт. Отработано {hours:.2f} ч.'
        + (' Отчёт за сегодня уже отправлен.' if workday.has_report else ' Не забудьте отправить отчёт до конца дня.')
    ), build_keyboard(workday, user)


def action_stats(user):
    error = _status_error(user)
    if error:
        return error, None
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    days = list(
        WorkDay.objects
        .filter(employee=user, date__gte=week_start, date__lte=today)
        .order_by('date')
    )
    if not days:
        return 'За текущую неделю рабочих дней пока нет.', None
    status_labels = dict(WorkDay.STATUS_CHOICES)
    weekday_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    lines = [f'Статистика с {week_start.strftime("%d.%m")} по {today.strftime("%d.%m")}:']
    total_seconds = 0
    for day in days:
        label = status_labels.get(day.status, day.status)
        hours = f'{day.total_work_hours:.2f} ч'
        report = '✅' if day.has_report else '—'
        weekday = weekday_names[day.date.weekday()]
        lines.append(f'{weekday} {day.date.strftime("%d.%m")}: {label}, {hours}, отчёт {report}')
        total_seconds += day.total_work_seconds
    lines.append(f'Всего за неделю: {round(total_seconds / 3600, 2)} ч')
    return '\n'.join(lines), None


def team_overview_text(company, day=None):
    """Today's roster for an administrator: who started, who did not."""
    from .models import WorkDay

    day = day or timezone.localdate()
    workdays = {
        wd.employee_id: wd
        for wd in WorkDay.objects.filter(company=company, date=day).select_related('employee')
    }
    tracked = []
    employee = None
    for profile in company.employees.filter(is_active=True, user__is_active=True).select_related('user', 'role', 'office'):
        role = getattr(profile.role, 'code', '')
        if getattr(profile, 'attendance_exempt', False):
            continue
        if str(role) == '00003' and not getattr(profile, 'attendance_required', False):
            continue
        tracked.append(profile)
    status_labels = dict(WorkDay.STATUS_CHOICES)
    lines = [f'Кто на работе — {day.strftime("%d.%m.%Y")}:']
    for profile in sorted(tracked, key=lambda p: (p.user.get_full_name() or p.user.email)):
        wd = workdays.get(profile.user_id)
        name = profile.user.get_full_name() or profile.user.email
        if wd is None:
            lines.append(f'⚪ {name} — день не начат')
            continue
        label = status_labels.get(wd.status, wd.status)
        if wd.started_at:
            started = timezone.localtime(wd.started_at).strftime('%H:%M')
            label = f'{label} (с {started})'
        report = ' ✅ отчёт' if wd.has_report else ''
        lines.append(f'{"🟢" if wd.status in {WorkDay.STATUS_STARTED, WorkDay.STATUS_REPORT_SUBMITTED} else "🔵"} {name} — {label}{report}')
    if len(lines) == 1:
        lines.append('Сотрудников в учёте пока нет.')
    return '\n'.join(lines)


def action_team(user):
    if not is_admin_user(user):
        return 'Эта команда доступна только администраторам.', None
    employee = get_employee_profile(user)
    company = employee.company if employee and employee.company_id else None
    if company is None:
        return 'Не найдена компания сотрудника.', None
    return team_overview_text(company), build_keyboard(get_today_workday(user), user)


ACTIONS = {
    CALLBACK_START: action_start,
    CALLBACK_REPORT: action_report,
    CALLBACK_CLOSE: action_close,
    CALLBACK_STATS: action_stats,
    CALLBACK_TEAM: action_team,
}

TEXT_ACTIONS = {
    BUTTON_START: action_start,
    '/startday': action_start,
    BUTTON_REPORT: action_report,
    '/report': action_report,
    BUTTON_CLOSE: action_close,
    '/close': action_close,
    BUTTON_STATS: action_stats,
    '/stats': action_stats,
}


def handle_private_text(account, text):
    """Route a private-chat text message for a linked employee."""
    user = account.employee
    report_result = _submit_report_text(user, text)
    if report_result is not None:
        workday = get_today_workday(user)
        return report_result, build_keyboard(workday, user)
    stripped = str(text or '').strip()
    action = TEXT_ACTIONS.get(stripped)
    if action:
        return action(user)
    workday = get_today_workday(user)
    return HELP_TEXT, build_keyboard(workday, user)


def handle_callback(account, callback_data):
    action = ACTIONS.get(str(callback_data or '').strip())
    if not action:
        return 'Неизвестная команда. Откройте меню бота ещё раз.', None
    return action(account.employee)


def binding_success_reply(employee):
    name = employee.get_full_name() or employee.email
    workday = get_today_workday(employee)
    return (
        f'Telegram подключён к ManagerSL: {name}.\n'
        'Личные напоминания о рабочем дне включены. Управлять днём можно кнопками ниже.',
        build_keyboard(workday),
    )
