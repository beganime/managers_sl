"""Telegram-кнопки «Взять в обработку» / «Обработано» для заявок.

Уведомления с inline-кнопками отправляются через бота табеля (у него уже есть
webhook в ManagerSL с секретом), поэтому нажатия кнопок приходят обратно в
``apps.attendance.telegram_views.attendance_telegram_webhook`` и
маршрутизируются сюда через ``handle_callback_query``.

Формат callback_data: ``sl:ld:<id>:take|done`` (лид с сайта),
``sl:sub:<id>:take|done`` (экспресс-анкета из приложения).
"""
import logging

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.core.permissions import get_employee_profile, is_erp_admin

from .lead_bridge import enqueue_lead_to_elite_task
from .models import Lead

logger = logging.getLogger(__name__)

ACTION_TAKE = 'take'
ACTION_DONE = 'done'

MANAGER_DENIED = 'Ваш Telegram не привязан к ManagerSL. Подключите его в «Профиль» → «Подключить Telegram».'


def _bot_token() -> str:
    return getattr(settings, 'ATTENDANCE_TELEGRAM_BOT_TOKEN', '') or ''


def _bot_call(method: str, payload: dict) -> bool:
    token = _bot_token()
    if not token:
        return False
    base = getattr(settings, 'ATTENDANCE_TELEGRAM_API_BASE', 'https://api.telegram.org').rstrip('/')
    try:
        response = requests.post(f'{base}/bot{token}/{method}', json=payload, timeout=20)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Telegram %s failed: %s.', method, type(exc).__name__)
        return False
    if response.status_code == 200 and data.get('ok') is True:
        return True
    logger.warning('Telegram %s rejected: HTTP %s.', method, response.status_code)
    return False


def send_message_with_keyboard(chat_id, text: str, keyboard: list | None = None) -> bool:
    payload = {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True}
    if keyboard:
        payload['reply_markup'] = {'inline_keyboard': keyboard}
    return _bot_call('sendMessage', payload)


def answer_callback(callback_id: str, text: str) -> bool:
    return _bot_call('answerCallbackQuery', {'callback_query_id': callback_id, 'text': text, 'show_alert': True})


def edit_message(chat_id, message_id: int, text: str, keyboard: list | None = None) -> bool:
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'disable_web_page_preview': True}
    if keyboard:
        payload['reply_markup'] = {'inline_keyboard': keyboard}
    return _bot_call('editMessageText', payload)


def _lead_keyboard(lead: Lead) -> list:
    base = f'sl:ld:{lead.pk}'
    buttons = [
        [{'text': '✋ Взять в обработку', 'callback_data': f'{base}:{ACTION_TAKE}'}],
        [
            {'text': '✅ Обработано', 'callback_data': f'{base}:{ACTION_DONE}'},
            {'text': 'Открыть в ManagerSL', 'url': f'{settings.PORTAL_BASE_URL}/portal/incoming-leads/'},
        ],
    ]
    return buttons


def _lead_message(lead: Lead) -> str:
    source = str(lead.source) if lead.source_id else 'сайт'
    lines = [
        '📥 Новая заявка с сайта' if lead.source_id is None else f'📥 Новая заявка (источник: {source})',
        f'ФИО: {lead.full_name}',
        f'Телефон: {lead.phone}',
        f'Email: {lead.email or "—"}',
        f'Страна: {lead.interested_country or lead.country or "—"}',
        f'Программа: {lead.interested_program or "—"}',
        f'Комментарий: {lead.comment or "—"}',
    ]
    return '\n'.join(lines)


def _submission_message(submission) -> str:
    kind = submission.get_kind_display()
    stage = submission.get_stage_display()
    return '\n'.join([
        '📱 Новая заявка из приложения Students Life',
        f'Тип: {kind} / {stage}',
        f'ФИО: {submission.full_name}',
        f'Телефон: {submission.phone}',
        f'Email: {submission.email or "—"}',
        f'Год поступления: {submission.academic_year}',
    ])


def _submission_keyboard(submission) -> list:
    base = f'sl:sub:{submission.pk}'
    return [
        [{'text': '✋ Взять в обработку', 'callback_data': f'{base}:{ACTION_TAKE}'}],
        [
            {'text': '✅ Обработано', 'callback_data': f'{base}:{ACTION_DONE}'},
            {'text': 'Открыть в ManagerSL', 'url': f'{settings.PORTAL_BASE_URL}/portal/onboarding-submissions/{submission.pk}/'},
        ],
    ]


def _manager_name(user) -> str:
    return (user.get_full_name() or user.email).strip()


def _elite_task_note() -> str:
    """Строка-подсказка про Elite Task для ответа менеджеру."""
    if getattr(settings, 'ELITE_TASK_INTEGRATION_KEY', ''):
        return '\nЗаявка передана в Elite Task — задача появится у команды автоматически.'
    return ''


@shared_task(bind=True, name='crm.notify_new_lead_buttons', autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 4})
def notify_new_lead_buttons(self, lead_id: int) -> dict:
    lead = Lead.objects.select_related('source', 'manager').filter(pk=lead_id).first()
    if lead is None:
        return {'sent': False, 'reason': 'lead_missing'}
    chat_id = getattr(settings, 'ATTENDANCE_TELEGRAM_CHAT_ID', '')
    if not chat_id:
        return {'sent': False, 'reason': 'chat_not_configured'}
    ok = send_message_with_keyboard(chat_id, _lead_message(lead), _lead_keyboard(lead))
    return {'sent': ok}


@shared_task(bind=True, name='crm.notify_new_submission_buttons', autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 4})
def notify_new_submission_buttons(self, submission_id: int) -> dict:
    from apps.client_onboarding.models import OnboardingSubmission

    submission = OnboardingSubmission.objects.filter(pk=submission_id).first()
    if submission is None:
        return {'sent': False, 'reason': 'submission_missing'}
    chat_id = getattr(settings, 'ATTENDANCE_TELEGRAM_CHAT_ID', '')
    if not chat_id:
        return {'sent': False, 'reason': 'chat_not_configured'}
    ok = send_message_with_keyboard(chat_id, _submission_message(submission), _submission_keyboard(submission))
    return {'sent': ok}


def queue_lead_buttons_notification(lead: Lead) -> None:
    lead_id = lead.pk
    transaction.on_commit(lambda: _safe_delay(notify_new_lead_buttons, lead_id))


def queue_submission_buttons_notification(submission) -> None:
    submission_id = submission.pk
    transaction.on_commit(lambda: _safe_delay(notify_new_submission_buttons, submission_id))


def _safe_delay(task, pk) -> None:
    try:
        task.delay(pk)
    except Exception:
        logger.warning('Could not enqueue %s for pk=%s.', task.name, pk)


def _resolve_user(telegram_user_id):
    from apps.attendance.models import EmployeeTelegramAccount

    account = EmployeeTelegramAccount.objects.select_related('employee').filter(
        telegram_user_id=telegram_user_id, is_active=True,
    ).first()
    return account.employee if account else None


def handle_callback_query(update: dict) -> None:
    """Обрабатывает нажатие inline-кнопки заявки (вызывается из webhook)."""
    callback = update.get('callback_query') or {}
    callback_id = callback.get('id')
    sender = callback.get('from') or {}
    telegram_user_id = sender.get('id')
    data = str(callback.get('data') or '')
    parts = data.split(':')
    if len(parts) != 4 or parts[0] != 'sl' or parts[1] not in {'ld', 'sub'} or not parts[2].isdigit() or parts[3] not in {ACTION_TAKE, ACTION_DONE}:
        return
    if not callback_id or not telegram_user_id:
        return

    user = _resolve_user(telegram_user_id)
    if user is None:
        answer_callback(callback_id, MANAGER_DENIED)
        return

    model_kind, object_id, action = parts[1], parts[2], parts[3]
    message = callback.get('message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    message_id = message.get('message_id')

    if model_kind == 'ld':
        _handle_lead_action(callback_id, user, object_id, action, chat_id, message_id)
    else:
        _handle_submission_action(callback_id, user, object_id, action, chat_id, message_id)


def _employee_scope(user):
    employee = get_employee_profile(user)
    return (employee.company if employee else None, employee.office if employee else None)


def _handle_lead_action(callback_id, user, object_id, action, chat_id, message_id) -> None:
    lead = Lead.objects.select_related('manager').filter(pk=object_id).first()
    if lead is None:
        answer_callback(callback_id, 'Заявка не найдена (возможно, удалена).')
        return
    name = _manager_name(user)
    if action == ACTION_TAKE:
        if lead.manager_id and lead.manager_id != user.id:
            answer_callback(callback_id, f'Заявка уже в работе у {_manager_name(lead.manager)}.')
            return
        company, office = _employee_scope(user)
        lead.take_responsibility(user, company=company, office=office)
        enqueue_lead_to_elite_task(lead.pk)
        answer_callback(callback_id, f'Вы взяли заявку «{lead.full_name}».{_elite_task_note()}')
        if chat_id and message_id:
            edit_message(chat_id, message_id, f'{_lead_message(lead)}\n\n✅ В работе: {name}', keyboard=None)
        return

    # action == done
    if lead.manager_id and lead.manager_id != user.id and not is_erp_admin(user):
        answer_callback(callback_id, 'Отметить «обработано» может ответственный менеджер или администратор.')
        return
    if hasattr(lead, 'client') and lead.client:
        lead.mark_converted(user=user)
        result_text = 'переведена в клиентов'
    else:
        lead.archive(user=user, reason='Обработано через Telegram')
        result_text = 'заархивирована как обработанная'
    lead.log_action('processed_via_telegram', user, save=True)
    answer_callback(callback_id, f'Заявка «{lead.full_name}» {result_text}.')
    if chat_id and message_id:
        edit_message(chat_id, message_id, f'{_lead_message(lead)}\n\n✅ Обработано: {name}', keyboard=None)


def _handle_submission_action(callback_id, user, object_id, action, chat_id, message_id) -> None:
    from django.utils import timezone
    from apps.client_onboarding.models import OnboardingSubmission

    submission = OnboardingSubmission.objects.filter(pk=object_id).first()
    if submission is None:
        answer_callback(callback_id, 'Заявка не найдена (возможно, удалена).')
        return
    name = _manager_name(user)
    if action == ACTION_TAKE:
        if submission.status not in {OnboardingSubmission.STATUS_SUBMITTED, OnboardingSubmission.STATUS_IN_REVIEW}:
            answer_callback(callback_id, f'Заявка уже в статусе «{submission.get_status_display()}».')
            return
        submission.status = OnboardingSubmission.STATUS_IN_REVIEW
        submission.reviewed_by = user
        submission.reviewed_at = timezone.now()
        submission.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
        answer_callback(callback_id, f'Вы взяли заявку «{submission.full_name}».')
        if chat_id and message_id:
            edit_message(chat_id, message_id, f'{_submission_message(submission)}\n\n✅ В работе: {name}', keyboard=None)
        return

    if submission.reviewed_by_id and submission.reviewed_by_id != user.id and not is_erp_admin(user):
        answer_callback(callback_id, 'Отметить «обработано» может ответственный менеджер или администратор.')
        return
    submission.status = OnboardingSubmission.STATUS_PROCESSED
    submission.reviewed_by = user
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
    answer_callback(callback_id, f'Заявка «{submission.full_name}» обработана.')
    if chat_id and message_id:
        edit_message(chat_id, message_id, f'{_submission_message(submission)}\n\n✅ Обработано: {name}', keyboard=None)
