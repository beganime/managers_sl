import hashlib
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.client_onboarding.models import OnboardingSubmission
from apps.client_onboarding.services import review_submission
from apps.crm.models import Client
from apps.education.models import City, Program, University
from users.models import User

from .client import GoogleSheetsGateway
from .models import ClientAdmissionSnapshot, SheetRowBinding, SheetSyncRun
from .schema import (
    GENERAL_HEADERS,
    ONBOARDING_HEADERS,
    ONBOARDING_STATUS_OPTIONS,
    OFFICE_CODES,
    REFERENCE_COLUMNS,
    university_acronym,
)


logger = logging.getLogger(__name__)

ONBOARDING_INTERNAL_STATUS_LABELS = {
    OnboardingSubmission.STATUS_SUBMITTED: 'Ожидание',
    OnboardingSubmission.STATUS_IN_REVIEW: 'Ожидание',
    OnboardingSubmission.STATUS_CHANGES_REQUESTED: 'Требуются изменения',
    OnboardingSubmission.STATUS_APPROVED: 'Подтвержден',
    OnboardingSubmission.STATUS_REJECTED: 'Отклонен',
}

ONBOARDING_SHEET_DECISIONS = {
    'подтвержден': 'approve',
    'подтверждено': 'approve',
    'одобрен': 'approve',
    'одобрена': 'approve',
    'approved': 'approve',
    'требуются изменения': 'request_changes',
    'вернуть на исправление': 'request_changes',
    'отклонен': 'reject',
    'отклонена': 'reject',
    'rejected': 'reject',
}

GENERAL_CREATE_ONLY_HEADERS = {
    'Имеется договор',
    'Какой договор',
    'Плата за услугу',
    'Валюта услуги',
    'Статус сейчас',
    'В какой город приглашение',
    'Встреча',
    'Где находится сейчас',
    'Замечание',
    'Комментарий',
    'Отказник',
}

# This is deliberately narrower than the columns used by managers. Passport,
# finance, credentials and internal comments must never cross this boundary.
GENERAL_PUBLIC_STATUS_FIELDS = {
    'current_status': 'Статус сейчас',
    'invitation_city': 'В какой город приглашение',
    'meeting': 'Встреча',
    'current_location': 'Где находится сейчас',
}

MANUAL_CLIENT_SHEET = 'Новые клиенты'
MANUAL_CLIENT_HEADERS = (
    'Статус', 'ФИО', 'Телефон', 'Email', 'Год поступления', 'Тип клиента',
    'Ответственный', 'Нужные услуги', 'Комментарий', 'Внутренний ID',
    'SL-ID', 'Логин', 'Пароль', 'Результат обработки', 'Добавлено',
)

SHEET_LAYOUTS = {
    'Заявки из анкеты': {
        'hidden_headers': ('Внутренний ID',),
        'column_widths': {
            'ФИО абитуриента': 210,
            'Вузы и программы': 360,
            'Ответственный': 190,
            'Комментарий менеджера': 260,
            'Что хочет клиент': 300,
        },
    },
    'Общее': {
        'column_widths': {
            'ФИО абитуриента': 210,
            'Куда поступает': 360,
            'Контакты студента': 230,
            'Контакты родителя': 230,
            'Замечание': 260,
            'Комментарий': 260,
        },
    },
    MANUAL_CLIENT_SHEET: {
        'hidden_headers': ('Внутренний ID',),
        'column_widths': {
            'ФИО': 210,
            'Нужные услуги': 240,
            'Комментарий': 280,
            'Ответственный': 190,
        },
    },
    'Справочники': {
        'column_widths': {
            'Ответственные': 210,
            'Университеты': 360,
            'Программы': 360,
        },
    },
}


def sheets_sync_enabled():
    return bool(
        settings.GOOGLE_SHEETS_ENABLED
        and settings.GOOGLE_SHEETS_SPREADSHEET_ID
        and settings.GOOGLE_SHEETS_CREDENTIALS_FILE
    )


def manager_sheet_options():
    return [
        display_user(user)
        for user in User.objects.filter(is_active=True)
        .filter(Q(role='manager') | Q(role='admin') | Q(is_superuser=True))
        .order_by('first_name', 'last_name', 'email')
    ]


def ensure_operational_sheet(gateway, sheet_name, headers):
    created = gateway.ensure_sheet(sheet_name, headers)
    if created and hasattr(gateway, 'format_sheet'):
        gateway.format_sheet(sheet_name, **SHEET_LAYOUTS.get(sheet_name, {}))


def display_user(user):
    if not user:
        return ''
    return user.get_full_name().strip() or user.email


def payload_value(payload, *keys, default=''):
    for key in keys:
        value = (payload or {}).get(key)
        if value not in (None, '', [], {}):
            return value
    return default


def as_yes_no(value):
    if value in (None, ''):
        return ''
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {'да', 'yes', 'true', '1', 'загружены', 'загружено'}:
            return 'Да'
        if normalized in {'нет', 'no', 'false', '0', 'не загружены', 'не загружено'}:
            return 'Нет'
    return 'Да' if bool(value) else 'Нет'


def normalize_funding(value):
    normalized = str(value or '').strip().casefold()
    mapping = {
        'гос': 'Государственная линия',
        'гослиния': 'Государственная линия',
        'государственная линия': 'Государственная линия',
        'б': 'Бюджет',
        'бюджет': 'Бюджет',
        'к': 'Контракт',
        'контракт': 'Контракт',
    }
    return mapping.get(normalized, str(value or '').strip())


def office_code(office):
    if not office:
        return ''
    source = f'{office.name} {office.city}'.casefold()
    for fragment, code in OFFICE_CODES.items():
        if fragment in source:
            return code
    return office.name or office.city


def serialize_value(value):
    if value is None:
        return ''
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, 'strftime'):
        if hasattr(value, 'hour'):
            return timezone.localtime(value).strftime('%d.%m.%Y %H:%M')
        return value.strftime('%d.%m.%Y')
    if isinstance(value, (list, tuple, set)):
        return ', '.join(str(item) for item in value if str(item).strip())
    return value


def values_hash(values):
    normalized = {key: serialize_value(value) for key, value in sorted(values.items())}
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def submission_general_values(submission):
    client = submission.client
    payload = submission.payload or {}
    try:
        snapshot_location = submission.client.admission_snapshot.current_location
    except ClientAdmissionSnapshot.DoesNotExist:
        snapshot_location = ''
    choices = list(submission.university_choices.all())
    admission_parts = []
    destination_cities = []
    for choice in choices:
        programs = list(choice.programs.all())
        program_names = ', '.join(program.name for program in programs)
        university_name = university_acronym(choice.university.name)
        admission_parts.append(
            f'{university_name}: {program_names}' if program_names else university_name
        )
        city = getattr(choice.university, 'city', None)
        if city and city.name not in destination_cities:
            destination_cities.append(city.name)

    student_contacts = [submission.phone]
    if submission.email:
        student_contacts.append(submission.email)
    messenger = payload_value(payload, 'messenger', 'social_contact', 'student_messenger')
    if messenger:
        student_contacts.append(str(messenger))

    parent_parts = []
    for value in (
        payload_value(payload, 'parent_full_name', 'relative_full_name', 'parent_name'),
        payload_value(payload, 'parent_relation', 'relative_relation'),
        payload_value(payload, 'parent_phone', 'relative_phone'),
        payload_value(payload, 'parent_messenger', 'relative_messenger'),
    ):
        if value:
            parent_parts.append(str(value))

    service_fee = payload_value(payload, 'service_fee', 'service_price', default='')
    service_currency = payload_value(payload, 'service_currency', 'currency', default='USD' if service_fee else '')
    updated_at = timezone.localtime(submission.updated_at).strftime('%d.%m.%Y %H:%M')

    return {
        'Айди': client.sl_id,
        'Внутренний ID': str(submission.public_id),
        'Год поступления': submission.academic_year,
        'Ответственный': display_user(client.manager),
        'ФИО абитуриента': submission.full_name,
        'Куда поступает': '; '.join(admission_parts),
        'Город поступления': ', '.join(destination_cities),
        'Дата рождения': serialize_value(submission.date_of_birth),
        'Номер паспорта': payload_value(payload, 'passport_number', 'passport_inter_num', 'passport'),
        'Город рождения': payload_value(payload, 'birth_city', 'passport_birth_place', 'birth_place'),
        'Где проживает сейчас': payload_value(payload, 'current_residence', 'current_city', 'address'),
        'Загружены документы': as_yes_no(payload_value(payload, 'documents_uploaded', 'cloud_uploaded', default='')),
        'Гос/б/к': client.get_funding_type_display() if client.funding_type else normalize_funding(payload_value(payload, 'funding_type', 'admission_type', 'gos_b_k')),
        'В каком офисе оформили': office_code(client.office),
        'Контакты студента': ', '.join(str(item) for item in student_contacts if item),
        'Контакты родителя': ', '.join(parent_parts),
        'Кто подавал': payload_value(payload, 'submitted_by', 'applicant_role', default='Клиент'),
        'Имеется договор': as_yes_no(payload_value(payload, 'has_contract', default=False)),
        'Какой договор': payload_value(payload, 'contract_type'),
        'Плата за услугу': serialize_value(service_fee),
        'Валюта услуги': service_currency,
        'Статус сейчас': payload_value(payload, 'current_status', default='Анкета подтверждена'),
        'Встреча': as_yes_no(payload_value(payload, 'meeting_required', 'has_meeting', default='')),
        'Где находится сейчас': snapshot_location or payload_value(payload, 'current_location'),
        'Замечание': payload_value(payload, 'note', 'remark'),
        'Комментарий': payload_value(payload, 'comment'),
        'Отказник': 'Нет',
        'Обновлено': updated_at,
        'Версия': 1,
    }


def submission_onboarding_values(submission):
    choices = []
    for choice in submission.university_choices.all():
        program_names = ', '.join(program.name for program in choice.programs.all())
        university_name = university_acronym(choice.university.name)
        choices.append(
            f'{choice.rank}. {university_name}: {program_names}'
            if program_names
            else f'{choice.rank}. {university_name}'
        )
    payload = submission.payload or {}
    return {
        'Внутренний ID': str(submission.public_id),
        'Этап': submission.get_stage_display(),
        'Раздел': 'Школьники' if submission.kind == OnboardingSubmission.KIND_SCHOOL_STUDENT else 'Поступление',
        'Тип анкеты': submission.get_kind_display(),
        'Год поступления': submission.academic_year,
        'ФИО абитуриента': submission.full_name,
        'Телефон': submission.phone,
        'Email': submission.email,
        'Дата рождения': serialize_value(submission.date_of_birth),
        'Гражданство': submission.citizenship,
        'Нужные услуги': serialize_value(payload.get('requested_services', [])),
        'Что хочет клиент': payload.get('request_text', ''),
        'Вузы и программы': ' | '.join(choices),
        'Ответственный': display_user(submission.reviewed_by) if submission.reviewed_by_id else '',
        'Комментарий менеджера': submission.review_comment,
        'SL-ID': submission.client.sl_id if submission.client_id else '',
        'Отправлено': serialize_value(submission.submitted_at),
        'Обновлено': serialize_value(submission.updated_at),
    }


def normalize_sheet_status(value):
    return str(value or '').strip().casefold().replace('ё', 'е')


def resolve_sheet_reviewer(values):
    requested = str(values.get('Ответственный', '') or '').strip().casefold()
    reviewers = list(
        User.objects.filter(is_active=True)
        .filter(Q(role='manager') | Q(role='admin') | Q(is_superuser=True))
        .select_related('employee_profile')
        .order_by('-is_superuser', 'first_name', 'last_name', 'email')
    )
    if requested:
        for reviewer in reviewers:
            if requested in {
                reviewer.email.casefold(),
                display_user(reviewer).casefold(),
            }:
                return reviewer
        raise ValidationError(
            'Ответственный из Google Sheets не найден среди активных менеджеров.'
        )
    if reviewers:
        # Sheets does not expose which employee edited a cell. Use the primary
        # administrator as a technical reviewer when only the status was set.
        return reviewers[0]
    raise ValidationError('Нет активного менеджера для подтверждения заявки.')


def _finish_run(run, *, status, processed=0, failed=0, error=''):
    run.status = status
    run.processed = processed
    run.failed = failed
    run.error = str(error)[:10000]
    run.finished_at = timezone.now()
    run.save(update_fields=['status', 'processed', 'failed', 'error', 'finished_at', 'updated_at'])
    return run


def sync_reference_data(gateway=None):
    run = SheetSyncRun.objects.create(kind=SheetSyncRun.KIND_REFERENCES)
    if not sheets_sync_enabled() and gateway is None:
        _finish_run(run, status=SheetSyncRun.STATUS_SKIPPED, error='Google Sheets отключён.')
        return {'status': 'skipped', 'processed': 0}

    try:
        gateway = gateway or GoogleSheetsGateway()
        sheet_name = settings.GOOGLE_SHEETS_REFERENCE_SHEET
        users = [
            display_user(user)
            for user in User.objects.filter(is_active=True).filter(Q(role='manager') | Q(role='admin')).order_by('first_name', 'last_name', 'email')
        ]
        cities = list(City.objects.filter(is_active=True).order_by('name').values_list('name', flat=True).distinct())
        universities = list(University.objects.filter(is_active=True).order_by('name').values_list('name', flat=True).distinct())
        programs = list(
            Program.objects.filter(is_active=True, is_archived=False)
            .order_by('name')
            .values_list('name', flat=True)
            .distinct()
        )
        groups = {
            'Ответственные': users,
            'Города': cities,
            'Университеты': universities,
            'Программы': programs,
        }
        processed = 0
        for header, values in groups.items():
            processed += gateway.replace_reference_column(
                sheet_name,
                REFERENCE_COLUMNS[header],
                header,
                values,
            )
        _finish_run(run, status=SheetSyncRun.STATUS_SUCCESS, processed=processed)
        return {'status': 'success', 'processed': processed}
    except Exception as exc:
        _finish_run(run, status=SheetSyncRun.STATUS_FAILED, failed=1, error=exc)
        raise


def sync_onboarding_submission(
    submission_id,
    gateway=None,
    *,
    force_status=False,
    processing_result=None,
    prepare_sheet=True,
):
    run = SheetSyncRun.objects.create(
        kind=SheetSyncRun.KIND_ONBOARDING_INBOX,
        object_ref=str(submission_id),
    )
    if not sheets_sync_enabled() and gateway is None:
        _finish_run(run, status=SheetSyncRun.STATUS_SKIPPED, error='Google Sheets отключён.')
        return {'status': 'skipped', 'processed': 0}

    try:
        submission = (
            OnboardingSubmission.objects.select_related('client', 'reviewed_by')
            .prefetch_related(
                'university_choices__university',
                'university_choices__programs',
            )
            .get(pk=submission_id)
        )
        gateway = gateway or GoogleSheetsGateway()
        sheet_name = settings.GOOGLE_SHEETS_ONBOARDING_SHEET
        if prepare_sheet:
            ensure_operational_sheet(gateway, sheet_name, ONBOARDING_HEADERS)
            gateway.set_dropdown_validation(
                sheet_name,
                'Статус',
                ONBOARDING_STATUS_OPTIONS,
            )
            gateway.set_dropdown_validation(
                sheet_name,
                'Ответственный',
                manager_sheet_options(),
                input_message='Выберите ответственного менеджера.',
            )

        values = submission_onboarding_values(submission)
        create_only_values = {
            'Статус': ONBOARDING_INTERNAL_STATUS_LABELS[submission.status],
            'Ответственный': '',
            'Результат обработки': '',
        }
        if force_status or submission.status not in {
            OnboardingSubmission.STATUS_SUBMITTED,
            OnboardingSubmission.STATUS_IN_REVIEW,
        }:
            values['Статус'] = ONBOARDING_INTERNAL_STATUS_LABELS[submission.status]
        if processing_result is not None:
            values['Результат обработки'] = str(processing_result)

        row_number, created = gateway.upsert_row(
            sheet_name,
            'Внутренний ID',
            str(submission.public_id),
            values,
            create_only_values=create_only_values,
        )
        _finish_run(run, status=SheetSyncRun.STATUS_SUCCESS, processed=1)
        return {
            'status': 'success',
            'processed': 1,
            'row_number': row_number,
            'created': created,
        }
    except Exception as exc:
        _finish_run(run, status=SheetSyncRun.STATUS_FAILED, failed=1, error=exc)
        raise


def sync_onboarding_inbox(limit=1000, gateway=None):
    run = SheetSyncRun.objects.create(kind=SheetSyncRun.KIND_ONBOARDING_INBOX)
    if not sheets_sync_enabled() and gateway is None:
        _finish_run(run, status=SheetSyncRun.STATUS_SKIPPED, error='Google Sheets отключён.')
        return {'status': 'skipped', 'processed': 0, 'failed': 0}

    try:
        gateway = gateway or GoogleSheetsGateway()
        sheet_name = settings.GOOGLE_SHEETS_ONBOARDING_SHEET
        ensure_operational_sheet(gateway, sheet_name, ONBOARDING_HEADERS)
        gateway.set_dropdown_validation(
            sheet_name,
            'Статус',
            ONBOARDING_STATUS_OPTIONS,
        )
        gateway.set_dropdown_validation(
            sheet_name,
            'Ответственный',
            manager_sheet_options(),
            input_message='Выберите ответственного менеджера.',
        )
        existing_ids = {
            str(row['values'].get('Внутренний ID', '') or '').strip()
            for row in gateway.read_rows(sheet_name)
        }
        submissions = list(
            OnboardingSubmission.objects.order_by('-updated_at')[:max(int(limit), 1)]
        )
        processed = 0
        failed = 0
        for submission in submissions:
            if str(submission.public_id) in existing_ids:
                continue
            try:
                sync_onboarding_submission(
                    submission.pk,
                    gateway=gateway,
                    prepare_sheet=False,
                )
                processed += 1
            except Exception:
                failed += 1
                logger.exception(
                    'Не удалось записать входящую анкету %s в Google Sheets.',
                    submission.pk,
                )
        result_status = SheetSyncRun.STATUS_SUCCESS if not failed else SheetSyncRun.STATUS_FAILED
        _finish_run(run, status=result_status, processed=processed, failed=failed)
        return {
            'status': 'success' if not failed else 'partial',
            'processed': processed,
            'failed': failed,
        }
    except Exception as exc:
        _finish_run(run, status=SheetSyncRun.STATUS_FAILED, failed=1, error=exc)
        raise


def import_onboarding_decisions(limit=1000, gateway=None):
    run = SheetSyncRun.objects.create(kind=SheetSyncRun.KIND_ONBOARDING_DECISIONS)
    if not sheets_sync_enabled() and gateway is None:
        _finish_run(run, status=SheetSyncRun.STATUS_SKIPPED, error='Google Sheets отключён.')
        return {'status': 'skipped', 'processed': 0, 'failed': 0}

    try:
        gateway = gateway or GoogleSheetsGateway()
        manual_result = import_manual_clients(gateway=gateway, limit=limit)
        sheet_name = settings.GOOGLE_SHEETS_ONBOARDING_SHEET
        ensure_operational_sheet(gateway, sheet_name, ONBOARDING_HEADERS)
        gateway.set_dropdown_validation(
            sheet_name,
            'Статус',
            ONBOARDING_STATUS_OPTIONS,
        )
        gateway.set_dropdown_validation(
            sheet_name,
            'Ответственный',
            manager_sheet_options(),
            input_message='Выберите ответственного менеджера.',
        )
        rows = gateway.read_rows(sheet_name)[:max(int(limit), 1)]
        processed = manual_result['processed']
        failed = manual_result['failed']
        for row in rows:
            values = row['values']
            public_id = str(values.get('Внутренний ID', '') or '').strip()
            normalized_status = normalize_sheet_status(values.get('Статус'))
            if not public_id or normalized_status in {'', 'ожидание', 'на проверке'}:
                continue
            decision = ONBOARDING_SHEET_DECISIONS.get(normalized_status)
            if not decision:
                failed += 1
                gateway.upsert_row(
                    sheet_name,
                    'Внутренний ID',
                    public_id,
                    {'Результат обработки': 'Неизвестный статус. Выберите значение из списка.'},
                )
                continue

            try:
                submission = OnboardingSubmission.objects.get(public_id=public_id)
                target_statuses = {
                    'approve': OnboardingSubmission.STATUS_APPROVED,
                    'request_changes': OnboardingSubmission.STATUS_CHANGES_REQUESTED,
                    'reject': OnboardingSubmission.STATUS_REJECTED,
                }
                target_status = target_statuses[decision]
                changed = submission.status != target_status
                if changed:
                    if submission.status not in {
                        OnboardingSubmission.STATUS_SUBMITTED,
                        OnboardingSubmission.STATUS_IN_REVIEW,
                    }:
                        raise ValidationError(
                            f'Анкета уже имеет статус «{submission.get_status_display()}».'
                        )
                    comment = str(values.get('Комментарий менеджера', '') or '').strip()
                    if decision in {'request_changes', 'reject'} and not comment:
                        raise ValidationError('Для этого статуса заполните комментарий менеджера.')
                    reviewer = resolve_sheet_reviewer(values)
                    submission = review_submission(
                        submission,
                        reviewer,
                        decision,
                        comment=comment,
                        enqueue_sync=False,
                    )
                    if decision == 'approve' and submission.client_id:
                        sync_submission(submission.pk, gateway=gateway)
                    processed += 1

                timestamp = timezone.localtime().strftime('%d.%m.%Y %H:%M')
                message = (
                    f'Обработано {timestamp}'
                    if changed
                    else f'Уже обработано ранее · проверено {timestamp}'
                )
                sync_onboarding_submission(
                    submission.pk,
                    gateway=gateway,
                    force_status=True,
                    processing_result=message,
                    prepare_sheet=False,
                )
            except Exception as exc:
                failed += 1
                logger.exception('Не удалось обработать решение по анкете %s.', public_id)
                message = '; '.join(getattr(exc, 'messages', [])) or str(exc)
                gateway.upsert_row(
                    sheet_name,
                    'Внутренний ID',
                    public_id,
                    {'Результат обработки': f'Ошибка: {message}'[:1000]},
                )

        result_status = SheetSyncRun.STATUS_SUCCESS if not failed else SheetSyncRun.STATUS_FAILED
        _finish_run(run, status=result_status, processed=processed, failed=failed)
        return {
            'status': 'success' if not failed else 'partial',
            'processed': processed,
            'failed': failed,
        }
    except Exception as exc:
        _finish_run(run, status=SheetSyncRun.STATUS_FAILED, failed=1, error=exc)
        raise


def import_manual_clients(*, gateway, limit=1000):
    ensure_operational_sheet(gateway, MANUAL_CLIENT_SHEET, MANUAL_CLIENT_HEADERS)
    gateway.set_dropdown_validation(MANUAL_CLIENT_SHEET, 'Статус', ('Новый', 'Создан', 'Ошибка'))
    gateway.set_dropdown_validation(
        MANUAL_CLIENT_SHEET,
        'Ответственный',
        manager_sheet_options(),
        input_message='Выберите ответственного менеджера.',
    )
    processed = 0
    failed = 0
    for row in gateway.read_rows(MANUAL_CLIENT_SHEET)[:max(int(limit), 1)]:
        values = row['values']
        if normalize_sheet_status(values.get('Статус')) != 'новый' or values.get('Внутренний ID'):
            continue
        try:
            full_name = str(values.get('ФИО') or '').strip()
            phone = str(values.get('Телефон') or '').strip()
            if not full_name or not phone:
                raise ValidationError('Заполните ФИО и телефон.')
            academic_year = int(values.get('Год поступления') or timezone.localdate().year + 1)
            kind = (
                OnboardingSubmission.KIND_SCHOOL_STUDENT
                if normalize_sheet_status(values.get('Тип клиента')) == 'школьник'
                else OnboardingSubmission.KIND_APPLICANT
            )
            services = [item.strip() for item in str(values.get('Нужные услуги') or 'Консультация').split(',') if item.strip()]
            comment = str(values.get('Комментарий') or '').strip()
            raw_token, token_hash = OnboardingSubmission.issue_access_token()
            submission = OnboardingSubmission.objects.create(
                access_token_hash=token_hash,
                kind=kind,
                stage=OnboardingSubmission.STAGE_EXPRESS,
                academic_year=academic_year,
                full_name=full_name,
                phone=phone,
                email=str(values.get('Email') or '').strip(),
                payload={
                    'requested_services': services,
                    'request_text': comment or 'Клиент добавлен менеджером для последующего заполнения анкеты.',
                    'source': 'google_sheets_manual',
                },
            )
            reviewer = resolve_sheet_reviewer(values)
            from apps.client_onboarding.services import approve_submission

            submission = approve_submission(
                submission,
                reviewer,
                enqueue_sync=False,
                onboarding_access_token=raw_token,
            )
            identity = submission.service_identity
            gateway.update_row(MANUAL_CLIENT_SHEET, row['row_number'], {
                'Статус': 'Создан',
                'Внутренний ID': str(submission.public_id),
                'SL-ID': submission.client.sl_id,
                'Логин': identity.mobile_login,
                'Пароль': identity.shared_password,
                'Результат обработки': 'Клиент и аккаунт созданы',
                'Добавлено': timezone.localtime().strftime('%d.%m.%Y %H:%M'),
            })
            sync_submission(submission.pk, gateway=gateway)
            processed += 1
        except Exception as exc:
            failed += 1
            gateway.update_row(MANUAL_CLIENT_SHEET, row['row_number'], {
                'Статус': 'Ошибка',
                'Результат обработки': f'Ошибка: {str(exc)}'[:1000],
            })
    return {'processed': processed, 'failed': failed}


def sync_submission(submission_id, gateway=None):
    run = SheetSyncRun.objects.create(
        kind=SheetSyncRun.KIND_SUBMISSION,
        object_ref=str(submission_id),
    )
    if not sheets_sync_enabled() and gateway is None:
        _finish_run(run, status=SheetSyncRun.STATUS_SKIPPED, error='Google Sheets отключён.')
        return {'status': 'skipped', 'processed': 0}

    try:
        submission = (
            OnboardingSubmission.objects.select_related('client', 'client__manager', 'client__office')
            .prefetch_related(
                'university_choices__university__city',
                'university_choices__programs',
            )
            .get(pk=submission_id)
        )
        if submission.status != OnboardingSubmission.STATUS_APPROVED or not submission.client_id:
            _finish_run(
                run,
                status=SheetSyncRun.STATUS_SKIPPED,
                error='Анкета ещё не одобрена или клиент не создан.',
            )
            return {'status': 'skipped', 'processed': 0}

        gateway = gateway or GoogleSheetsGateway()
        general_sheet = settings.GOOGLE_SHEETS_GENERAL_SHEET
        ensure_operational_sheet(gateway, general_sheet, GENERAL_HEADERS)
        general_values = submission_general_values(submission)
        create_only_values = {
            header: general_values.pop(header)
            for header in GENERAL_CREATE_ONLY_HEADERS
            if header in general_values
        }
        row_number, _ = gateway.upsert_row(
            general_sheet,
            'Айди',
            submission.client.sl_id,
            general_values,
            create_only_values=create_only_values,
        )
        SheetRowBinding.objects.update_or_create(
            spreadsheet_id=gateway.spreadsheet_id,
            sheet_name=general_sheet,
            entity_type=SheetRowBinding.ENTITY_CLIENT,
            object_ref=str(submission.client_id),
            defaults={
                'sl_id': submission.client.sl_id,
                'row_number': row_number,
                'row_hash': values_hash(general_values),
                'last_synced_at': timezone.now(),
            },
        )

        processed = 1
        _finish_run(run, status=SheetSyncRun.STATUS_SUCCESS, processed=processed)
        return {'status': 'success', 'processed': processed}
    except Exception as exc:
        _finish_run(run, status=SheetSyncRun.STATUS_FAILED, failed=1, error=exc)
        raise


def sync_pending_submissions(limit=100, gateway=None):
    run = SheetSyncRun.objects.create(kind=SheetSyncRun.KIND_PENDING)
    if not sheets_sync_enabled() and gateway is None:
        _finish_run(run, status=SheetSyncRun.STATUS_SKIPPED, error='Google Sheets отключён.')
        return {'status': 'skipped', 'processed': 0, 'failed': 0}

    try:
        bound_client_refs = SheetRowBinding.objects.filter(
            spreadsheet_id=(gateway.spreadsheet_id if gateway else settings.GOOGLE_SHEETS_SPREADSHEET_ID),
            sheet_name=settings.GOOGLE_SHEETS_GENERAL_SHEET,
            entity_type=SheetRowBinding.ENTITY_CLIENT,
        ).values_list('object_ref', flat=True)
        bound_client_ids = [int(value) for value in bound_client_refs if str(value).isdigit()]
        submissions = list(
            OnboardingSubmission.objects.filter(
                status=OnboardingSubmission.STATUS_APPROVED,
                client__isnull=False,
            )
            .exclude(client_id__in=bound_client_ids)
            .order_by('reviewed_at')[:limit]
        )
        gateway = gateway or GoogleSheetsGateway()
        processed = 0
        failed = 0
        for submission in submissions:
            try:
                result = sync_submission(submission.pk, gateway=gateway)
                processed += result.get('processed', 0)
            except Exception:
                failed += 1
                logger.exception('Не удалось синхронизировать анкету %s.', submission.pk)
        status = SheetSyncRun.STATUS_SUCCESS if not failed else SheetSyncRun.STATUS_FAILED
        _finish_run(run, status=status, processed=processed, failed=failed)
        return {
            'status': 'success' if not failed else 'partial',
            'processed': processed,
            'failed': failed,
        }
    except Exception as exc:
        _finish_run(run, status=SheetSyncRun.STATUS_FAILED, failed=1, error=exc)
        raise


def import_public_client_statuses(limit=1000, gateway=None):
    """Import only client-safe operational fields from the general sheet."""
    run = SheetSyncRun.objects.create(kind=SheetSyncRun.KIND_PUBLIC_STATUS)
    if not sheets_sync_enabled() and gateway is None:
        _finish_run(run, status=SheetSyncRun.STATUS_SKIPPED, error='Google Sheets отключён.')
        return {'status': 'skipped', 'processed': 0, 'failed': 0}

    try:
        gateway = gateway or GoogleSheetsGateway()
        sheet_name = settings.GOOGLE_SHEETS_GENERAL_SHEET
        rows = gateway.read_rows(sheet_name)
        rows = [
            row for row in rows
            if str(row['values'].get('Айди', '')).strip()
        ][:max(int(limit), 1)]
        sl_ids = [str(row['values']['Айди']).strip() for row in rows]
        clients = {
            client.sl_id: client
            for client in Client.objects.filter(sl_id__in=sl_ids)
        }

        processed = 0
        failed = 0
        now = timezone.now()
        for row in rows:
            try:
                values = row['values']
                sl_id = str(values.get('Айди', '')).strip()
                client = clients.get(sl_id)
                if not client:
                    continue
                safe_values = {
                    field: str(values.get(header, '') or '').strip()
                    for field, header in GENERAL_PUBLIC_STATUS_FIELDS.items()
                }
                source_hash = values_hash(safe_values)
                snapshot, created = ClientAdmissionSnapshot.objects.get_or_create(
                    client=client,
                    defaults={
                        **safe_values,
                        'spreadsheet_id': gateway.spreadsheet_id,
                        'sheet_name': sheet_name,
                        'row_number': row['row_number'],
                        'source_hash': source_hash,
                        'source_updated_value': str(values.get('Обновлено', '') or '').strip(),
                        'last_imported_at': now,
                    },
                )
                changed = created or snapshot.source_hash != source_hash
                if not created:
                    for field, value in safe_values.items():
                        setattr(snapshot, field, value)
                    snapshot.spreadsheet_id = gateway.spreadsheet_id
                    snapshot.sheet_name = sheet_name
                    snapshot.row_number = row['row_number']
                    snapshot.source_hash = source_hash
                    snapshot.source_updated_value = str(values.get('Обновлено', '') or '').strip()
                    snapshot.last_imported_at = now
                    snapshot.save()

                SheetRowBinding.objects.update_or_create(
                    spreadsheet_id=gateway.spreadsheet_id,
                    sheet_name=sheet_name,
                    entity_type=SheetRowBinding.ENTITY_CLIENT,
                    object_ref=str(client.pk),
                    defaults={
                        'sl_id': sl_id,
                        'row_number': row['row_number'],
                        'last_synced_at': now,
                    },
                )
                if changed:
                    processed += 1
            except Exception:
                failed += 1
                logger.exception('Не удалось импортировать публичный статус строки %s.', row['row_number'])

        status = SheetSyncRun.STATUS_SUCCESS if not failed else SheetSyncRun.STATUS_FAILED
        _finish_run(run, status=status, processed=processed, failed=failed)
        return {
            'status': 'success' if not failed else 'partial',
            'processed': processed,
            'failed': failed,
        }
    except Exception as exc:
        _finish_run(run, status=SheetSyncRun.STATUS_FAILED, failed=1, error=exc)
        raise


def enqueue_submission_sync(submission_id):
    if not sheets_sync_enabled():
        return False
    try:
        from .tasks import sync_submission_task

        sync_submission_task.delay(submission_id)
        return True
    except Exception:
        logger.exception('Не удалось поставить синхронизацию анкеты %s в очередь.', submission_id)
        return False


def enqueue_onboarding_inbox_sync(submission_id, force_status=False):
    if not sheets_sync_enabled():
        return False
    try:
        from .tasks import sync_onboarding_submission_task

        sync_onboarding_submission_task.delay(submission_id, force_status=force_status)
        return True
    except Exception:
        logger.exception(
            'Не удалось поставить запись входящей анкеты %s в очередь.',
            submission_id,
        )
        return False
