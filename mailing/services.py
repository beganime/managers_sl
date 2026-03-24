# mailing/services.py
import logging
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.conf import settings

from clients.models import Client
from users.models import User
from .models import MailingCampaign, MailingLog

logger = logging.getLogger(__name__)

def _render(template_str: str, context: dict) -> str:
    result = template_str
    for key, value in context.items():
        result = result.replace('{{' + key + '}}', str(value or ''))
    return result

def _get_recipients(campaign: MailingCampaign) -> list[dict]:
    recipients = []
    if campaign.recipient_type == 'all_clients':
        qs = Client.objects.filter(email__isnull=False).exclude(email='')
        for c in qs:
            recipients.append({'email': c.email, 'first_name': c.full_name, 'last_name': '', 'office': ''})
    elif campaign.recipient_type == 'all_staff':
        qs = User.objects.filter(is_active=True).exclude(email='')
        for u in qs:
            recipients.append({'email': u.email, 'first_name': u.first_name, 'last_name': u.last_name, 'office': ''})
    elif campaign.recipient_type == 'custom_emails':
        raw = campaign.custom_emails.replace(',', '\n')
        for line in raw.splitlines():
            email = line.strip()
            if '@' in email:
                recipients.append({'email': email, 'first_name': 'Пользователь', 'last_name': '', 'office': ''})
    return recipients

def send_test_email(campaign: MailingCampaign, target_email: str):
    """Отправляет одно тестовое письмо админу"""
    tpl = campaign.template
    ctx = {'first_name': 'ТЕСТ', 'last_name': 'ТЕСТОВ', 'email': target_email, 'office': 'Главный офис'}
    
    subject = f"[ТЕСТ] {_render(tpl.subject, ctx)}"
    body_html = _render(tpl.body_html, ctx)
    body_text = _render(tpl.body_text, ctx) if tpl.body_text else 'Откройте письмо в HTML-клиенте.'

    msg = EmailMultiAlternatives(subject=subject, body=body_text, from_email=settings.DEFAULT_FROM_EMAIL, to=[target_email])
    if body_html:
        msg.attach_alternative(body_html, 'text/html')
    msg.send(fail_silently=False)

def send_campaign(campaign: MailingCampaign) -> None:
    campaign.status = 'sending'
    campaign.started_at = timezone.now()
    campaign.save(update_fields=['status', 'started_at'])

    recipients = _get_recipients(campaign)
    tpl = campaign.template
    sent, failed = 0, 0
    errors = []

    for r in recipients:
        ctx = {'first_name': r.get('first_name', ''), 'last_name': r.get('last_name', ''), 'email': r['email'], 'office': r.get('office', '')}
        subject = _render(tpl.subject, ctx)
        body_html = _render(tpl.body_html, ctx)
        body_text = _render(tpl.body_text, ctx) if tpl.body_text else ''

        try:
            msg = EmailMultiAlternatives(subject=subject, body=body_text, from_email=settings.DEFAULT_FROM_EMAIL, to=[r['email']])
            if body_html:
                msg.attach_alternative(body_html, 'text/html')
            msg.send(fail_silently=False)

            MailingLog.objects.create(campaign=campaign, email=r['email'], recipient_name=r.get('first_name',''), is_success=True)
            sent += 1
        except Exception as e:
            err_msg = str(e)
            MailingLog.objects.create(campaign=campaign, email=r['email'], recipient_name=r.get('first_name',''), is_success=False, error_msg=err_msg)
            failed += 1
            errors.append(f'{r["email"]}: {err_msg}')

    campaign.status = 'done' if failed == 0 else 'error'
    campaign.total_sent = sent
    campaign.total_failed = failed
    campaign.finished_at = timezone.now()
    campaign.error_log = '\n'.join(errors[:50])
    campaign.save(update_fields=['status', 'total_sent', 'total_failed', 'finished_at', 'error_log']) 