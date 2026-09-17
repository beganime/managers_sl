import json
from django.core.management.base import BaseCommand
from apps.crm.identity_reconciliation import reconcile_applications


class Command(BaseCommand):
    help = 'Conservative exact FK matching. Default dry-run; never splits or merges applications.'

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--apply', action='store_true')
        mode.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(reconcile_applications(apply=options['apply']), ensure_ascii=False, indent=2))
