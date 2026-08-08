import requests

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.crm.models import Client
from apps.erp_notifications.push import send_push_to_token

from .models import OnboardingSubmission


def post_service(url, token, payload):
    if not url or not token:
        return {'status': 'disabled'}
    response = requests.post(
        url,
        json=payload,
        headers={'Authorization': f'Bearer {token}'},
        timeout=settings.SERVICE_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


@shared_task(
    bind=True,
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def provision_client_services(self, client_id, event_id):
    client = Client.objects.get(pk=client_id)
    data = dict(client.custom_data or {})
    mobile = post_service(
        settings.STUDENTS_LIFE_PROVISION_API_URL,
        settings.STUDENTS_LIFE_PROVISION_TOKEN,
        {
            'event_id': event_id,
            'sl_id': client.sl_id,
            'password': data['mobile_password'],
            'full_name': client.full_name,
            'email': client.email or '',
            'phone': client.phone,
        },
    )
    mail = {'status': 'not_required'}
    if data.get('onboarding_kind') != 'school_student':
        mail = post_service(
            f'{settings.SMTP_SL_API_BASE_URL}/api/v1/tmmail/provision/' if settings.SMTP_SL_API_BASE_URL else '',
            settings.SMTP_SL_SERVICE_TOKEN,
            {
                'event_id': event_id,
                'sl_id': client.sl_id,
                'email': data['tmmail_email'],
                'password': data['tmmail_password'],
                'display_name': client.full_name,
            },
        )
    data['service_provisioning'] = {
        'mobile': mobile.get('status', 'ok'),
        'tmmail': mail.get('status', 'ok'),
        'updated_at': timezone.now().isoformat(),
    }
    Client.objects.filter(pk=client.pk).update(custom_data=data)
    return data['service_provisioning']


@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_jitter=True)
def notify_onboarding_status(self, submission_id):
    submission = OnboardingSubmission.objects.select_related('client').get(pk=submission_id)
    if not submission.fcm_token:
        return {'status': 'skipped', 'reason': 'missing_token'}

    if submission.status == OnboardingSubmission.STATUS_APPROVED:
        title = 'Аккаунт одобрен'
        body = f'Ваш идентификатор — {submission.client.sl_id}. Получите пароль у менеджера.'
    elif submission.status == OnboardingSubmission.STATUS_CHANGES_REQUESTED:
        title = 'Нужно исправить анкету'
        body = submission.review_comment or 'Менеджер оставил комментарий к вашей анкете.'
    elif submission.status == OnboardingSubmission.STATUS_REJECTED:
        title = 'Решение по анкете'
        body = submission.review_comment or 'Анкета отклонена. Обратитесь к менеджеру.'
    else:
        return {'status': 'skipped', 'reason': 'status_not_notifiable'}

    try:
        sent = send_push_to_token(
            submission.fcm_token,
            title,
            body,
            data={
                'type': 'onboarding_status',
                'public_id': str(submission.public_id),
                'status': submission.status,
                'sl_id': submission.client.sl_id if submission.client_id else '',
            },
        )
    except Exception as exc:
        raise self.retry(exc=exc)
    return {'status': 'sent' if sent else 'disabled'}
