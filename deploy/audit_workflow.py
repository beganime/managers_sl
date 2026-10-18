"""Read-only production audit for onboarding and Google Sheets integration."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "students_life.settings")

import django

django.setup()

from django.conf import settings
from django.db.models import Count

from apps.client_onboarding.models import ClientProvisioningStep, OnboardingSubmission
from apps.crm.models import Client
from apps.sheets_sync.client import GoogleSheetsGateway
from apps.sheets_sync.models import SheetSyncRun
from apps.sheets_sync.schema import EXAM_HEADERS, FINANCE_HEADERS, GENERAL_HEADERS, ONBOARDING_HEADERS


def grouped_counts(queryset, field):
    return {
        row[field]: row["count"]
        for row in queryset.values(field).annotate(count=Count("id")).order_by(field)
    }


def main():
    print("ManagerSL workflow audit")
    print(f"clients={Client.objects.count()}")
    print(f"clients_without_sl_id={Client.objects.filter(sl_id__isnull=True).count() + Client.objects.filter(sl_id='').count()}")
    print(f"onboarding_statuses={grouped_counts(OnboardingSubmission.objects.all(), 'status')}")
    print(f"onboarding_stages={grouped_counts(OnboardingSubmission.objects.all(), 'stage')}")
    print(f"provisioning_statuses={grouped_counts(ClientProvisioningStep.objects.all(), 'status')}")
    print(f"failed_provisioning={ClientProvisioningStep.objects.filter(status=ClientProvisioningStep.STATUS_FAILED).count()}")
    print(f"failed_sheet_runs={SheetSyncRun.objects.filter(status=SheetSyncRun.STATUS_FAILED).count()}")
    for step in ClientProvisioningStep.objects.filter(
        status=ClientProvisioningStep.STATUS_FAILED,
    ).values("id", "submission_id", "step", "attempt_count", "last_error")[:10]:
        error = str(step["last_error"] or "").replace("\n", " ")[:300]
        print(
            f"provisioning_error_id={step['id']}; submission_id={step['submission_id']}; "
            f"step={step['step']}; attempts={step['attempt_count']}; error={error}"
        )
    failed_sheet_errors = (
        SheetSyncRun.objects.filter(status=SheetSyncRun.STATUS_FAILED)
        .values("kind", "error")
        .annotate(count=Count("id"))
        .order_by("-count", "kind")[:10]
    )
    for failure in failed_sheet_errors:
        error = str(failure["error"] or "").replace("\n", " ")[:300]
        print(f"sheet_error={failure['kind']}; count={failure['count']}; error={error}")

    gateway = GoogleSheetsGateway()
    health = gateway.health_check()
    print(f"spreadsheet={health['title']}; sheets={len(health['sheets'])}")

    contracts = {
        settings.GOOGLE_SHEETS_GENERAL_SHEET: GENERAL_HEADERS,
        settings.GOOGLE_SHEETS_ONBOARDING_SHEET: ONBOARDING_HEADERS,
        settings.GOOGLE_SHEETS_FINANCE_SHEET: FINANCE_HEADERS,
        settings.GOOGLE_SHEETS_EXAMS_SHEET: EXAM_HEADERS,
    }
    errors = []
    for sheet_name, expected_headers in contracts.items():
        if sheet_name not in health["sheets"]:
            errors.append(f"missing sheet: {sheet_name}")
            continue
        headers = gateway.headers(sheet_name)
        missing = [header for header in expected_headers if header not in headers]
        row_count = len(gateway.read_rows(sheet_name))
        print(f"sheet={sheet_name}; rows={row_count}; columns={len(headers)}; missing_headers={len(missing)}")
        if missing:
            errors.append(f"{sheet_name}: missing {', '.join(missing)}")

    if errors:
        print("AUDIT_FAILED")
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("AUDIT_OK")


if __name__ == "__main__":
    main()
