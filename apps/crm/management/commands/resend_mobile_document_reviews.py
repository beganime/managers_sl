from django.core.management.base import BaseCommand

from apps.crm.models import ClientFile
from apps.portal.views import notify_mobile_document_review


class Command(BaseCommand):
    help = 'Resend accepted/rejected mobile document review callbacks to the mobile backend.'

    def add_arguments(self, parser):
        parser.add_argument('--document-id', type=int, help='Resend one manager-sl ClientFile ID.')
        parser.add_argument('--mobile-document-id', type=int, help='Resend one mobile document ID.')
        parser.add_argument('--status', choices=[ClientFile.STATUS_APPROVED, ClientFile.STATUS_REJECTED], help='Filter by review status.')
        parser.add_argument('--limit', type=int, default=0, help='Maximum number of documents to resend. 0 means no limit.')
        parser.add_argument('--dry-run', action='store_true', help='Show documents without sending callbacks.')

    def handle(self, *args, **options):
        qs = (
            ClientFile.objects
            .select_related('client')
            .filter(
                source='students_life_mobile_app',
                external_mobile_document_id__isnull=False,
                status__in=[ClientFile.STATUS_APPROVED, ClientFile.STATUS_REJECTED],
            )
            .order_by('-reviewed_at', '-updated_at', '-id')
        )
        if options['document_id']:
            qs = qs.filter(pk=options['document_id'])
        if options['mobile_document_id']:
            qs = qs.filter(external_mobile_document_id=options['mobile_document_id'])
        if options['status']:
            qs = qs.filter(status=options['status'])
        if options['limit']:
            qs = qs[:options['limit']]

        total = sent = 0
        for document in qs:
            total += 1
            label = (
                f'id={document.id} mobile_document_id={document.external_mobile_document_id} '
                f'status={document.status} client={document.client.full_name}'
            )
            if options['dry_run']:
                self.stdout.write(self.style.NOTICE(f'DRY RUN {label}'))
                continue
            notify_mobile_document_review(document)
            sent += 1
            self.stdout.write(self.style.SUCCESS(f'Resent {label}'))

        self.stdout.write(self.style.SUCCESS(f'Done. total={total}, sent={sent}'))
