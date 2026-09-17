"""Outbound-only notifications: never change the existing website bot webhook."""
import logging
import os
import time

import requests
from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.crm.questionnaire_labels import QUESTIONNAIRE_DOCUMENT_LABELS, QUESTIONNAIRE_VALUE_LABELS
from .models import OnboardingSubmission

logger = logging.getLogger(__name__)


def notification_parts(submission):
    lines = [
        'Новая заявка из приложения Students Life',
        f'Тип: {submission.get_kind_display()}', f'Этап: {submission.get_stage_display()}',
        f'ФИО: {submission.full_name}', f'Телефон: {submission.phone}',
        f'Email: {submission.email or "—"}', f'Год поступления: {submission.academic_year}',
        f'Дата рождения: {submission.date_of_birth or "—"}',
        f'Гражданство: {submission.citizenship or "—"}',
    ]
    def flatten(value, prefix=''):
        if isinstance(value, dict):
            for key, item in value.items():
                if any(word in str(key).lower() for word in ('token', 'password', 'secret', 'credential')):
                    continue
                label = QUESTIONNAIRE_DOCUMENT_LABELS.get(key, key)
                flatten(item, f'{prefix} / {label}' if prefix else label)
        elif isinstance(value, list):
            for index, item in enumerate(value, 1):
                flatten(item, f'{prefix} {index}')
        else:
            lines.append(f'{prefix}: {QUESTIONNAIRE_VALUE_LABELS.get(value, value) if value is not None else "—"}')
    flatten(submission.payload or {})
    for choice in submission.university_choices.select_related('university').prefetch_related('programs'):
        lines.append(f'Вуз: {choice.university.name}; программы: {", ".join(p.name for p in choice.programs.all())}')
    text = '\n'.join(lines)
    # Stay below Telegram's UTF-16 limit even with emoji and supplementary characters.
    return [text[start:start + 1800] for start in range(0, len(text), 1800)]


def send_part(text, submission_id=None):
    token = os.environ.get('ONBOARDING_TELEGRAM_BOT_TOKEN', '')
    chat = os.environ.get('ONBOARDING_TELEGRAM_CHAT_ID', '')
    if not token or not chat:
        return False
    buttons = []
    if submission_id is not None:
        buttons.append([{'text': 'Обработать в ManagerSL', 'url': f'https://manager-sl.ru/portal/onboarding-submissions/{submission_id}/'}])
    workbook = getattr(settings, 'GOOGLE_SHEETS_SPREADSHEET_ID', '')
    if workbook:
        buttons.append([{'text': 'Открыть Google Sheets', 'url': f'https://docs.google.com/spreadsheets/d/{workbook}/edit'}])
    base = os.environ.get('ONBOARDING_TELEGRAM_API_BASE', 'https://api.telegram.org').rstrip('/')
    payload = {
        'chat_id': chat,
        'text': text,
        'disable_web_page_preview': True,
        'reply_markup': {'inline_keyboard': buttons},
    }
    # The ManagerSL host reaches Telegram through the outbound relay.  Short
    # intermittent relay failures must not silently lose an application alert.
    # Do not log the URL: it contains the bot token.
    for attempt in range(3):
        try:
            response = requests.post(f'{base}/bot{token}/sendMessage', json=payload, timeout=20)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning('Telegram onboarding transport failed (attempt %s/3, %s).', attempt + 1, type(exc).__name__)
        else:
            if response.status_code == 200 and data.get('ok') is True:
                return True
            # Telegram's error description is intentionally not persisted:
            # it can include values from a request in future API versions.
            logger.warning('Telegram onboarding rejected delivery (attempt %s/3, HTTP %s).', attempt + 1, response.status_code)
            # 4xx errors are deterministic (bad chat, permissions, payload),
            # apart from rate limiting; retrying them only creates duplicates.
            if response.status_code != 429 and response.status_code < 500:
                return False
        if attempt < 2:
            time.sleep(attempt + 1)
    return False


@shared_task
def notify_new_application(submission_id):
    with transaction.atomic():
        submission = OnboardingSubmission.objects.select_for_update().get(pk=submission_id)
        parts = notification_parts(submission)
        for index in range(submission.telegram_sent_parts, len(parts)):
            if not send_part(parts[index], submission.pk):
                logger.warning('Telegram onboarding delivery failed for submission %s', submission_id)
                return {'status': 'failed', 'sent_parts': index}
            submission.telegram_sent_parts = index + 1
            submission.save(update_fields=['telegram_sent_parts'])
    return {'status': 'sent'}


def enqueue_new_application(submission_id):
    try:
        notify_new_application.delay(submission_id)
    except Exception:
        logger.warning('Could not enqueue Telegram onboarding notification %s', submission_id)
