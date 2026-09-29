import hashlib
import json
import secrets

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import AttendanceTelegramDelivery, AttendanceTelegramTopic, EmployeeTelegramAccount, TelegramLinkCode


TOPIC_ALIASES = {
    'daily': AttendanceTelegramTopic.TOPIC_DAILY,
    'итоги': AttendanceTelegramTopic.TOPIC_DAILY,
    'reports': AttendanceTelegramTopic.TOPIC_REPORTS,
    'отчеты': AttendanceTelegramTopic.TOPIC_REPORTS,
    'отчёты': AttendanceTelegramTopic.TOPIC_REPORTS,
    'absent': AttendanceTelegramTopic.TOPIC_ABSENT,
    'непришедшие': AttendanceTelegramTopic.TOPIC_ABSENT,
    'time': AttendanceTelegramTopic.TOPIC_TIME,
    'время': AttendanceTelegramTopic.TOPIC_TIME,
}


def telegram_reply(chat_id, text, message_thread_id=None):
    # Telegram executes this method from the webhook response; no outbound API call is needed.
    payload = {'method': 'sendMessage', 'chat_id': chat_id, 'text': text}
    if message_thread_id:
        payload['message_thread_id'] = message_thread_id
    return JsonResponse(payload)


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
    if chat.get('type') in {'group', 'supergroup'}:
        expected_chat_id = str(settings.ATTENDANCE_TELEGRAM_CHAT_ID or '')
        thread_id = message.get('message_thread_id')
        command = text.split(maxsplit=1)
        command_name = command[0].split('@', 1)[0].lower()
        if command_name != '/topic' or str(chat_id) != expected_chat_id or not thread_id:
            # Never answer in General: topic routing must be configured from inside a topic.
            return JsonResponse({'ok': True})
        alias = command[1].strip().lower().replace(' ', '') if len(command) > 1 else ''
        topic_type = TOPIC_ALIASES.get(alias)
        if not topic_type:
            return telegram_reply(
                chat_id,
                'Укажите назначение: /topic daily, /topic reports, /topic absent или /topic time.',
                thread_id,
            )
        existing_thread = AttendanceTelegramTopic.objects.filter(
            chat_id=chat_id,
            message_thread_id=thread_id,
        ).exclude(topic_type=topic_type).first()
        if existing_thread:
            return telegram_reply(chat_id, 'Эта тема уже назначена для другого типа сообщений.', thread_id)
        AttendanceTelegramTopic.objects.update_or_create(
            chat_id=chat_id,
            topic_type=topic_type,
            defaults={
                'message_thread_id': thread_id,
                'title': str(message.get('reply_to_message', {}).get('forum_topic_created', {}).get('name') or '')[:128],
                'configured_by_telegram_user_id': telegram_user_id,
            },
        )
        from .telegram import _safe_delay, topic_type_for_event
        waiting_ids = []
        for delivery in AttendanceTelegramDelivery.objects.filter(
            target_chat_id__isnull=True,
            status=AttendanceTelegramDelivery.STATUS_FAILED,
            attempts__lt=5,
        ).only('pk', 'event_type'):
            if topic_type_for_event(delivery.event_type) == topic_type:
                waiting_ids.append(delivery.pk)
        if waiting_ids:
            AttendanceTelegramDelivery.objects.filter(pk__in=waiting_ids).update(
                status=AttendanceTelegramDelivery.STATUS_PENDING,
                attempts=0,
                last_error='',
            )
            transaction.on_commit(lambda: [_safe_delay(delivery_id) for delivery_id in waiting_ids])
        topic_name = dict(AttendanceTelegramTopic.TOPIC_CHOICES)[topic_type]
        return telegram_reply(
            chat_id,
            f'Готово. «{topic_name}» привязана к этой теме (ID {thread_id}).',
            thread_id,
        )
    if chat.get('type') != 'private':
        return JsonResponse({'ok': True})
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
