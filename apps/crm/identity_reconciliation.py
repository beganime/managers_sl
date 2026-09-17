"""Conservative phase-1 reconciliation. Never merge people by contact data."""
from collections import defaultdict
from uuid import uuid4

from django.db import transaction
from django.db.models import Q

from apps.education.models import University, Program
from .models import Client, Application


def duplicate_candidates(clients):
    buckets = defaultdict(list)
    for client in clients:
        for field in ('email', 'phone', 'passport_inter_num', 'mobile_app_user_id'):
            value = str(getattr(client, field, '') or '').strip().casefold()
            if value:
                buckets[(field, value)].append(client.pk)
        if client.dob and client.full_name.strip():
            buckets[('name_dob', (client.full_name.strip().casefold(), client.dob))].append(client.pk)
    # Do not export the identifying values, even as unsalted hashes.
    return [{'field': key[0], 'client_ids': ids} for key, ids in buckets.items() if len(ids) > 1]


@transaction.atomic
def reconcile_students(*, apply=False, eligible_ids=()):
    """UUIDs for all records, SL-IDs only for explicitly reviewed client PKs.

    Shared contacts are a conflict requiring manual review, not a merge signal.
    Lock ordering matches onboarding: sequence before any client updates.
    """
    from apps.client_onboarding.models import AcademicYearSequence, OnboardingSubmission
    from apps.client_onboarding.services import allocate_sl_id

    eligible_ids = set(eligible_ids)
    if apply and eligible_ids:
        AcademicYearSequence.objects.select_for_update().get_or_create(
            academic_year=0, kind=OnboardingSubmission.KIND_APPLICANT,
            defaults={'last_number': 0},
        )
    qs = Client.objects.order_by('pk')
    if apply:
        qs = qs.select_for_update()
    clients = list(qs)
    conflicts = duplicate_candidates(clients)
    blocked = {pk for conflict in conflicts for pk in conflict['client_ids']}
    known = {c.pk for c in clients}
    if eligible_ids - known:
        raise ValueError('Unknown eligible client IDs; no changes applied.')
    before = {'records': len(clients), 'missing_uuid': sum(c.public_id is None for c in clients),
              'missing_sl_id': sum(not c.sl_id for c in clients)}
    actions = []
    for client in clients:
        fields = {}
        if client.public_id is None:
            fields['public_id'] = uuid4()
        needs_sl = not client.sl_id and client.pk in eligible_ids and client.pk not in blocked
        if needs_sl and apply:
            fields['sl_id'] = allocate_sl_id(0, OnboardingSubmission.KIND_APPLICANT)
        if fields or needs_sl:
            actions.append({'client_id': client.pk, 'uuid_assigned': 'public_id' in fields,
                            'sl_id_assigned': needs_sl})
        if apply and fields:
            Client.objects.filter(pk=client.pk).update(**fields)
    return {'schema_version': 1, 'mode': 'apply' if apply else 'dry-run', 'before': before,
            'actions': actions, 'conflicts': conflicts,
            'unreviewed_client_ids': [c.pk for c in clients if not c.sl_id and c.pk not in eligible_ids],
            'after': {'records': Client.objects.count(), 'missing_uuid': Client.objects.filter(public_id=None).count(),
                      'missing_sl_id': Client.objects.filter(Q(sl_id=None) | Q(sl_id='')).count()}}


def application_mapping(application):
    """Only exact, unique, company-scoped matches; compound program text stays unresolved."""
    university = application.university
    if university is None:
        label = application.university_name.strip()
        if not label:
            return {}, 'missing_university'
        matches = list(University.objects.filter(
            Q(company_id=None) | Q(company_id=application.company_id),
        ).filter(Q(name__iexact=label) | Q(abbreviation__iexact=label))[:2])
        if len(matches) != 1:
            return {}, 'ambiguous_or_unmatched_university'
        university = matches[0]
    if university.company_id not in (None, application.company_id):
        return {}, 'university_company_conflict'
    if application.country_reference_id and application.country_reference_id != university.country_id:
        return {}, 'country_conflict'
    if application.country.strip() and application.country.strip().casefold() != university.country.name.casefold():
        return {}, 'legacy_country_requires_review'
    program = application.program
    if program is None:
        label = application.program_name.strip()
        if not label:
            return {}, 'missing_program'
        matches = list(Program.objects.filter(university=university, name__iexact=label)[:2])
        if len(matches) != 1:
            return {}, 'ambiguous_or_unmatched_program'
        program = matches[0]
    if program.university_id != university.pk:
        return {}, 'program_university_conflict'
    if application.company_id != application.client.company_id:
        return {}, 'client_company_conflict'
    return {'university_id': university.pk, 'program_id': program.pk,
            'country_reference_id': university.country_id}, None


@transaction.atomic
def reconcile_applications(*, apply=False):
    qs = Application.objects.order_by('pk')
    if apply:
        qs = qs.select_for_update()
    actions, conflicts = [], []
    before = {'records': qs.count(), 'missing_uuid': qs.filter(public_id=None).count(),
              'missing_program': qs.filter(program=None).count()}
    for application in qs:
        mapping, issue = application_mapping(application)
        changes = {key: value for key, value in mapping.items() if getattr(application, key) != value}
        if issue:
            conflicts.append({'application_id': application.pk, 'reason': issue})
        if application.public_id is None:
            changes['public_id'] = uuid4()
        if changes:
            actions.append({'application_id': application.pk, 'fields': sorted(changes)})
            if apply:
                Application.objects.filter(pk=application.pk).update(**changes)
    return {'schema_version': 1, 'mode': 'apply' if apply else 'dry-run', 'before': before,
            'actions': actions, 'conflicts': conflicts,
            'after': {'records': Application.objects.count(), 'missing_uuid': Application.objects.filter(public_id=None).count(),
                      'missing_program': Application.objects.filter(program=None).count()}}
