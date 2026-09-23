import hashlib
import json
import secrets

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import EmployeeTelegramAccount, TelegramLinkCode


def telegram_reply(chat_id, text):
    # Telegram executes this method from the webhook response; no outbound API call is needed.
    return JsonResponse({'method': 'sendMessage', 'chat_id': chat_id, 'text': text})


@csrf_exempt
@require_POST
def attendance_telegram_webhook(request):
    expected = settings.ATTENDANCE_TELEGRAM_WEBHOOK_SECRET
    supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if not expected or not secrets.compare_digest(expected, supplied):
        return HttpResponseForbidden()
    try:
        update = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest()
    message = update.get('message') or {}
    chat = message.get('chat') or {}
    sender = message.get('from') or {}
    text = str(message.get('text') or '').strip()
    chat_id = chat.get('id')
    telegram_user_id = sender.get('id')
    if not chat_id or not telegram_user_id or not text:
        return JsonResponse({'ok': True})
    if chat.get('type') != 'private':
        return telegram_reply(chat_id, 'Подключение аккаунта доступно только в личном чате с ботом.')
    if text == '/start':
        return telegram_reply(
            chat_id,
            'Откройте «Профиль» в ManagerSL, нажмите «Подключить Telegram» и перейдите по одноразовой ссылке.',
        )
    if not text.startswith('/start '):
        return telegram_reply(chat_id, 'Для подключения используйте одноразовую ссылку из профиля ManagerSL.')

    raw_code = text.split(maxsplit=1)[1].strip()
    code_hash = hashlib.sha256(raw_code.encode()).hexdigest()
    with transaction.atomic():
        link = TelegramLinkCode.objects.select_for_update().select_related('employee').filter(
            code_hash=code_hash,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()
        if not link:
            return telegram_reply(chat_id, 'Ссылка недействительна или истекла. Создайте новую в профиле ManagerSL.')
        conflict = EmployeeTelegramAccount.objects.filter(telegram_user_id=telegram_user_id).exclude(employee=link.employee).exists()
        if conflict:
            return telegram_reply(chat_id, 'Этот Telegram уже подключён к другому сотруднику. Обратитесь к администратору.')
        EmployeeTelegramAccount.objects.update_or_create(
            employee=link.employee,
            defaults={
                'telegram_user_id': telegram_user_id,
                'chat_id': chat_id,
                'username': str(sender.get('username') or '')[:64],
                'first_name': str(sender.get('first_name') or '')[:128],
                'last_name': str(sender.get('last_name') or '')[:128],
                'linked_at': timezone.now(),
                'is_active': True,
            },
        )
        link.used_at = timezone.now()
        link.save(update_fields=['used_at', 'updated_at'])
    name = link.employee.get_full_name() or link.employee.email
    return telegram_reply(chat_id, f'Telegram подключён к ManagerSL: {name}. Вы будете получать личные напоминания о рабочем дне.')
