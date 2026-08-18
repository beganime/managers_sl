"""Retry failed onboarding provisioning steps without exposing client data."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "students_life.settings")

import django

django.setup()

from apps.client_onboarding.models import ClientProvisioningStep, OnboardingSubmission
from apps.client_onboarding.tasks import provision_client_services


def main():
    submission_ids = list(
        ClientProvisioningStep.objects.filter(
            status=ClientProvisioningStep.STATUS_FAILED,
        )
        .values_list("submission_id", flat=True)
        .distinct()
    )
    print(f"failed_submissions={len(submission_ids)}")
    for submission in OnboardingSubmission.objects.filter(pk__in=submission_ids).only(
        "id", "client_id", "public_id"
    ):
        result = provision_client_services.run(submission.client_id, str(submission.public_id))
        print(f"submission_id={submission.id}; result={result}")


if __name__ == "__main__":
    main()
