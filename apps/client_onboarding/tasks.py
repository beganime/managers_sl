from datetime import timedelta

import requests

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.crm.models import Client
from apps.erp_notifications.push import send_push_to_token

from .models import ClientProvisioningStep, OnboardingSubmission


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


PROVISIONING_LEASE = timedelta(minutes=5)


def claim_provisioning_step(submission, step_name):
    with transaction.atomic():
        step, _ = ClientProvisioningStep.objects.select_for_update().get_or_create(
            submission=submission,
            step=step_name,
            defaults={
                'client': submission.client,
                'event_id': f'{submission.public_id}:{step_name}',
            },
        )
        if step.status in {
            ClientProvisioningStep.STATUS_SUCCESS,
            ClientProvisioningStep.STATUS_NOT_REQUIRED,
        }:
            return step, False
        if (
            step.status == ClientProvisioningStep.STATUS_RUNNING
            and step.started_at
            and step.started_at >= timezone.now() - PROVISIONING_LEASE
        ):
            return step, False
        step.status = ClientProvisioningStep.STATUS_RUNNING
        step.attempt_count = F('attempt_count') + 1
        step.started_at = timezone.now()
        step.finished_at = None
        step.last_error = ''
        step.save(update_fields=[
            'status', 'attempt_count', 'started_at', 'finished_at',
            'last_error', 'updated_at',
        ])
        step.refresh_from_db()
        return step, True


def finish_provisioning_step(step, status, response=None, error=''):
    step.status = status
    step.response_data = response or {}
    step.last_error = str(error or '')[:10000]
    step.finished_at = timezone.now()
    step.save(update_fields=[
        'status', 'response_data', 'last_error', 'finished_at', 'updated_at',
    ])
    return step


def execute_service_step(submission, step_name):
    step, claimed = claim_provisioning_step(submission, step_name)
    if not claimed:
        return step

    client = submission.client
    data = dict(client.custom_data or {})
    try:
        if step_name == ClientProvisioningStep.STEP_MOBILE_ACCOUNT:
            response = post_service(
                settings.STUDENTS_LIFE_PROVISION_API_URL,
                settings.STUDENTS_LIFE_PROVISION_TOKEN,
                {
                    'event_id': step.event_id,
                    'sl_id': client.sl_id,
                    'password': data['mobile_password'],
                    'full_name': client.full_name,
                    'email': client.email or '',
                    'phone': client.phone,
                },
            )
        elif step_name == ClientProvisioningStep.STEP_TMMAIL:
            if data.get('onboarding_kind') == OnboardingSubmission.KIND_SCHOOL_STUDENT:
                return finish_provisioning_step(
                    step,
                    ClientProvisioningStep.STATUS_NOT_REQUIRED,
                    {'status': 'not_required'},
                )
            response = post_service(
                f'{settings.SMTP_SL_API_BASE_URL}/api/v1/tmmail/provision/' if settings.SMTP_SL_API_BASE_URL else '',
                settings.SMTP_SL_SERVICE_TOKEN,
                {
                    'event_id': step.event_id,
                    'sl_id': client.sl_id,
                    'email': data['tmmail_email'],
                    'password': data['tmmail_password'],
                    'display_name': client.full_name,
                },
            )
        else:
            raise ValueError('Unknown provisioning step.')
        status = (
            ClientProvisioningStep.STATUS_DISABLED
            if response.get('status') == 'disabled'
            else ClientProvisioningStep.STATUS_SUCCESS
        )
        return finish_provisioning_step(step, status, response)
    except Exception as exc:
        return finish_provisioning_step(
            step,
            ClientProvisioningStep.STATUS_FAILED,
            error=exc,
        )


@shared_task(name='client_onboarding.provision_client_services')
def provision_client_services(client_id, event_id=''):
    client = Client.objects.get(pk=client_id)
    submission = OnboardingSubmission.objects.select_related('client').get(client=client)
    data = dict(client.custom_data or {})
    mobile_step = execute_service_step(submission, ClientProvisioningStep.STEP_MOBILE_ACCOUNT)
    mail_step = execute_service_step(submission, ClientProvisioningStep.STEP_TMMAIL)
    data['service_provisioning'] = {
        'mobile': mobile_step.status,
        'tmmail': mail_step.status,
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
