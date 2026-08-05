import hashlib
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.client_onboarding.models import OnboardingSubmission
from apps.education.models import City, Program, University
from users.models import User

from .client import GoogleSheetsGateway
from .models import SheetRowBinding, SheetSyncRun
from .schema import (
    GENERAL_HEADERS,
    OFFICE_CODES,
    REFERENCE_COLUMNS,
    UNIVERSITY_HEADERS,
    safe_sheet_title,
    university_acronym,
)


logger = logging.getLogger(__name__)

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


def sheets_sync_enabled():
    return bool(
        settings.GOOGLE_SHEETS_ENABLED
        and settings.GOOGLE_SHEETS_SPREADSHEET_ID
        and settings.GOOGLE_SHEETS_CREDENTIALS_FILE
    )


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
    choices = list(submission.university_choices.all())
    admission_parts = []
    destination_cities = []
    for choice in choices:
        programs = list(choice.programs.all())
        program_names = ', '.join(program.name for program in programs)
        admission_parts.append(
            f'{choice.university.name}: {program_names}' if program_names else choice.university.name
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
        'Гос/б/к': normalize_funding(payload_value(payload, 'funding_type', 'admission_type', 'gos_b_k')),
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
        'Где находится сейчас': payload_value(payload, 'current_location'),
        'Замечание': payload_value(payload, 'note', 'remark'),
        'Комментарий': payload_value(payload, 'comment'),
        'Отказник': 'Нет',
        'Обновлено': updated_at,
        'Версия': 1,
    }


def university_row_values(submission, choice):
    client = submission.client
    programs = list(choice.programs.all())
    degree_names = []
    for program in programs:
        degree = program.get_degree_display()
        if degree not in degree_names:
            degree_names.append(degree)
    return {
        'Айди': client.sl_id,
        'Внутренний ID': str(submission.public_id),
        'Ответственный': display_user(client.manager),
        'ФИО': submission.full_name,
        'Уровень образования': ', '.join(degree_names),
        'Направления': ', '.join(program.name for program in programs),
        'Статус подачи в вуз': 'Черновик',
        'Обновлено': timezone.localtime(submission.updated_at).strftime('%d.%m.%Y %H:%M'),
        'Версия': 1,
    }


def resolve_university_sheet_name(gateway, university):
    custom_data = university.custom_data or {}
    explicit = str(custom_data.get('google_sheet_name') or '').strip()
    titles = gateway.sheet_titles()
    candidates = [explicit, university_acronym(university.name), university.name]
    for candidate in candidates:
        if candidate and candidate in titles:
            return candidate
    return safe_sheet_title(explicit or university.name)


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
        gateway.ensure_sheet(general_sheet, GENERAL_HEADERS)
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
        applications = {
            str(item.custom_data.get('onboarding_choice_id')): item
            for item in submission.client.applications.all()
            if item.custom_data.get('onboarding_choice_id')
        }
        for choice in submission.university_choices.all():
            sheet_name = resolve_university_sheet_name(gateway, choice.university)
            gateway.ensure_sheet(sheet_name, UNIVERSITY_HEADERS)
            row_values = university_row_values(submission, choice)
            row_number, _ = gateway.upsert_row(
                sheet_name,
                'Айди',
                submission.client.sl_id,
                row_values,
            )
            application = applications.get(str(choice.id))
            object_ref = str(application.pk if application else choice.pk)
            SheetRowBinding.objects.update_or_create(
                spreadsheet_id=gateway.spreadsheet_id,
                sheet_name=sheet_name,
                entity_type=SheetRowBinding.ENTITY_APPLICATION,
                object_ref=object_ref,
                defaults={
                    'sl_id': submission.client.sl_id,
                    'row_number': row_number,
                    'row_hash': values_hash(row_values),
                    'last_synced_at': timezone.now(),
                },
            )
            processed += 1

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
