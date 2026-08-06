import re
import secrets

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.crm.models import Application, Client, ClientQuestionnaire
from apps.organizations.models import Company

from .models import AcademicYearSequence, OnboardingSubmission


CYRILLIC_TO_LATIN = str.maketrans({
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'ä': 'a', 'ç': 'c', 'ň': 'n', 'ö': 'o', 'ş': 's', 'ü': 'u', 'ý': 'y',
})


def latin_name(value, fallback='student'):
    normalized = str(value or '').strip().casefold().translate(CYRILLIC_TO_LATIN)
    normalized = re.sub(r'[^a-z0-9]+', '', normalized)
    return normalized or fallback


def build_service_credentials(submission, sl_id):
    name_parts = submission.full_name.split()
    first_name = latin_name(name_parts[0] if name_parts else '', 'student')
    last_name = latin_name(name_parts[-1] if len(name_parts) > 1 else '', 'client')
    suffix = str(submission.date_of_birth.year) if submission.date_of_birth else sl_id.rsplit('-', 1)[-1]
    return {
        'mobile_login': sl_id,
        'mobile_password': f'{first_name.capitalize()}_0710',
        'tmmail_email': f'{first_name}.{last_name}{suffix}@tmmail.ru',
        'tmmail_password': secrets.token_urlsafe(18),
    }


def resolve_review_company(reviewer, company_id=None):
    employee = getattr(reviewer, 'employee_profile', None)
    if employee:
        if company_id and company_id != employee.company_id and not reviewer.is_superuser:
            raise ValidationError('Менеджер не может создавать клиента другой компании.')
        return employee.company, employee.office

    queryset = Company.objects.filter(is_active=True)
    if company_id:
        company = queryset.filter(pk=company_id).first()
        if not company:
            raise ValidationError('Активная компания не найдена.')
        return company, None
    if queryset.count() == 1:
        return queryset.get(), None
    raise ValidationError('Нужно указать company_id или создать профиль сотрудника.')


def allocate_sl_id(academic_year, kind):
    sequence_year = int(academic_year)
    sequence, _ = AcademicYearSequence.objects.select_for_update().get_or_create(
        academic_year=sequence_year,
        kind=kind,
        defaults={'last_number': 0},
    )
    sequence.last_number += 1
    sequence.save(update_fields=['last_number'])
    if kind == OnboardingSubmission.KIND_SCHOOL_STUDENT:
        return f'SL-SCHOOL-{sequence_year}-{sequence.last_number:03d}'
    return f'SL-{sequence_year}-{sequence.last_number:03d}'


@transaction.atomic
def approve_submission(submission, reviewer, company_id=None):
    submission = (
        OnboardingSubmission.objects.select_for_update()
        .select_related('client')
        .get(pk=submission.pk)
    )
    if submission.status == OnboardingSubmission.STATUS_APPROVED:
        return submission
    if submission.status != OnboardingSubmission.STATUS_SUBMITTED:
        raise ValidationError('Одобрить можно только отправленную анкету.')

    company, office = resolve_review_company(reviewer, company_id)
    choices = list(
        submission.university_choices.select_related('university', 'university__country').prefetch_related('programs')
    )
    first_choice = choices[0] if choices else None
    sl_id = allocate_sl_id(submission.academic_year, submission.kind)
    credentials = build_service_credentials(submission, sl_id)
    client = Client.objects.create(
        company=company,
        office=office,
        manager=reviewer,
        full_name=submission.full_name,
        phone=submission.phone,
        email=submission.email or None,
        dob=submission.date_of_birth,
        citizenship=submission.citizenship,
        interested_country=first_choice.university.country.name if first_choice else '',
        interested_university=first_choice.university.name if first_choice else '',
        interested_program=', '.join(program.name for program in first_choice.programs.all()) if first_choice else '',
        mobile_app_source=True,
        sl_id=sl_id,
        academic_year=submission.academic_year,
        custom_data={
            'onboarding_public_id': str(submission.public_id),
            'onboarding_kind': submission.kind,
            **credentials,
        },
    )

    questionnaire_data = dict(submission.payload or {})
    questionnaire_data['university_choices'] = [
        {
            'university_id': choice.university_id,
            'university_name': choice.university.name,
            'programs': [{'id': program.id, 'name': program.name} for program in choice.programs.all()],
        }
        for choice in choices
    ]
    ClientQuestionnaire.objects.create(
        client=client,
        status=ClientQuestionnaire.STATUS_APPROVED,
        full_name=submission.full_name,
        phone=submission.phone,
        email=submission.email or None,
        citizenship=submission.citizenship,
        desired_program=client.interested_program,
        desired_country=client.interested_country,
        data=questionnaire_data,
        submitted_at=submission.submitted_at,
        last_synced_at=timezone.now(),
    )

    for choice in choices:
        programs = list(choice.programs.all())
        Application.objects.create(
            client=client,
            company=company,
            office=office,
            manager=reviewer,
            university_name=choice.university.name,
            program_name=', '.join(program.name for program in programs),
            country=choice.university.country.name,
            custom_data={
                'onboarding_choice_id': choice.id,
                'university_id': choice.university_id,
                'program_ids': [program.id for program in programs],
            },
        )

    submission.client = client
    submission.status = OnboardingSubmission.STATUS_APPROVED
    submission.reviewed_by = reviewer
    submission.reviewed_at = timezone.now()
    submission.review_comment = ''
    submission.save(update_fields=['client', 'status', 'reviewed_by', 'reviewed_at', 'review_comment', 'updated_at'])
    transaction.on_commit(lambda: _enqueue_submission_sync(submission.pk))
    transaction.on_commit(lambda: _enqueue_service_provisioning(client.pk, str(submission.public_id)))
    return submission


def _enqueue_submission_sync(submission_id):
    from apps.sheets_sync.services import enqueue_submission_sync

    enqueue_submission_sync(submission_id)


def _enqueue_service_provisioning(client_id, event_id):
    from .tasks import provision_client_services

    provision_client_services.delay(client_id, event_id)
