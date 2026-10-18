from datetime import timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.5,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=frozenset({'POST'}),
        raise_on_status=False,
    )
    with requests.Session() as session:
        session.mount('https://', HTTPAdapter(max_retries=retry))
        session.mount('http://', HTTPAdapter(max_retries=retry))
        response = session.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {token}'},
            timeout=settings.SERVICE_REQUEST_TIMEOUT,
        )
    response.raise_for_status()
    return response.json()


PROVISIONING_LEASE = timedelta(minutes=5)


def disk_category_for_submission(submission):
    payload = dict(submission.payload or {})
    education_level = str(
        payload.get('desired_education_level')
        or payload.get('education_level')
        or payload.get('degree')
        or ''
    ).strip().lower()
    if education_level in {'master', 'masters', 'магистр', 'магистратура'} or 'магистр' in education_level:
        return 'Магистры'

    funding = str(submission.client.funding_type or payload.get('funding_type') or '').strip().lower()
    if funding in {'government', 'гос', 'гослиния', 'государственная линия'}:
        return 'Гослиния'
    if funding in {'budget', 'бюджет'}:
        return 'Бюджет'
    return 'Контракт'


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
                    'fcm_token': submission.fcm_token or '',
                    'onboarding_public_id': str(submission.public_id),
                    'onboarding_access_token': data.get('onboarding_access_token', ''),
                    'onboarding_kind': data.get('onboarding_kind', OnboardingSubmission.KIND_APPLICANT),
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
        elif step_name == ClientProvisioningStep.STEP_DISK:
            response = post_service(
                settings.DISK_PROVISION_API_URL,
                settings.DISK_PROVISION_SERVICE_TOKEN,
                {
                    'event_id': step.event_id,
                    'academic_year': client.academic_year,
                    'sl_id': client.sl_id,
                    'full_name': client.full_name,
                    'category': disk_category_for_submission(submission),
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
    disk_step = execute_service_step(submission, ClientProvisioningStep.STEP_DISK)
    data['service_provisioning'] = {
        'mobile': mobile_step.status,
        'tmmail': mail_step.status,
        'disk': disk_step.status,
        'updated_at': timezone.now().isoformat(),
    }
    Client.objects.filter(pk=client.pk).update(custom_data=data)
    # Provisioning stores the latest FCM token and already attempts the first
    # credential push. If no device received it, enqueue a retry only after the
    # mobile account exists, avoiding the former provisioning/notification race.
    mobile_response = mobile_step.response_data or {}
    if 'push_sent' in mobile_response and not int(mobile_response.get('push_sent') or 0):
        notify_onboarding_status.run(submission.pk)
    return data['service_provisioning']


@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_jitter=True)
def notify_onboarding_status(self, submission_id):
    submission = OnboardingSubmission.objects.select_related('client', 'service_identity').get(pk=submission_id)

    if submission.status == OnboardingSubmission.STATUS_APPROVED:
        if submission.client_id:
            title = 'Аккаунт одобрен'
            try:
                identity = submission.service_identity
            except Exception:
                identity = None
            login = getattr(identity, 'mobile_login', '') or submission.client.sl_id
            password = getattr(identity, 'shared_password', '') or (submission.client.custom_data or {}).get('mobile_password', '')
            body = f'Ваш логин: {login}'
            if password:
                body += f'\nВаш пароль: {password}'
        else:
            title = 'Экспресс-заявка одобрена'
            body = 'Теперь можно заполнить полную анкету абитуриента.'
    elif submission.status == OnboardingSubmission.STATUS_CHANGES_REQUESTED:
        title = 'Нужно исправить анкету'
        body = submission.review_comment or 'Менеджер оставил комментарий к вашей анкете.'
    elif submission.status == OnboardingSubmission.STATUS_REJECTED:
        title = 'Решение по анкете'
        body = submission.review_comment or 'Анкета отклонена. Обратитесь к менеджеру.'
    else:
        return {'status': 'skipped', 'reason': 'status_not_notifiable'}

    try:
        if submission.client_id:
            response = post_service(
                settings.STUDENTS_LIFE_PROVISION_API_URL.replace('/provision/', '/notify/'),
                settings.STUDENTS_LIFE_PROVISION_TOKEN,
                {
                    'sl_id': submission.client.sl_id,
                    'title': title,
                    'body': body,
                    'notification_type': 'onboarding_status',
                    'public_id': str(submission.public_id),
                    'status': submission.status,
                },
            )
            return response
        if not submission.fcm_token:
            return {'status': 'skipped', 'reason': 'missing_token'}
        sent = send_push_to_token(
            submission.fcm_token, title, body,
            data={'type': 'onboarding_status', 'public_id': str(submission.public_id), 'status': submission.status},
        )
    except Exception as exc:
        raise self.retry(exc=exc)
    return {'status': 'sent' if sent else 'disabled'}
