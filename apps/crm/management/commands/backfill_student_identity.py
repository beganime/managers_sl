import json
from django.core.management.base import BaseCommand, CommandError
from apps.crm.identity_reconciliation import reconcile_students


class Command(BaseCommand):
    help = 'Read-only by default. Emits redacted reconciliation JSON. No merges or external calls.'

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--apply', action='store_true')
        mode.add_argument('--dry-run', action='store_true')
        parser.add_argument('--eligible-client-ids', nargs='+', type=int, default=[])

    def handle(self, *args, **options):
        try:
            report = reconcile_students(apply=options['apply'], eligible_ids=options['eligible_client_ids'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
