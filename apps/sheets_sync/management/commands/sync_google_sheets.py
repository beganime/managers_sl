from django.core.management.base import BaseCommand, CommandError

from apps.sheets_sync.client import GoogleSheetsGateway
from apps.sheets_sync.services import (
    import_public_client_statuses,
    sheets_sync_enabled,
    sync_pending_submissions,
    sync_reference_data,
    sync_submission,
)


class Command(BaseCommand):
    help = 'Проверяет подключение и синхронизирует ManagerSL с основной книгой Google Sheets.'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Только проверить доступ к книге.')
        parser.add_argument('--references', action='store_true', help='Обновить справочники.')
        parser.add_argument('--pending', action='store_true', help='Добавить ещё не синхронизированные анкеты.')
        parser.add_argument('--import-public', action='store_true', help='Импортировать безопасные статусы клиентов.')
        parser.add_argument('--submission', type=int, help='Синхронизировать одну одобренную анкету по ID.')
        parser.add_argument('--limit', type=int, default=100, help='Лимит для --pending (по умолчанию 100).')

    def handle(self, *args, **options):
        if not sheets_sync_enabled():
            raise CommandError(
                'Google Sheets отключён. Заполните GOOGLE_SHEETS_* и установите '
                'GOOGLE_SHEETS_ENABLED=True.'
            )

        requested = any(
            (
                options['check'],
                options['references'],
                options['pending'],
                options['import_public'],
                options['submission'],
            )
        )
        if not requested:
            options['check'] = True

        gateway = GoogleSheetsGateway()
        if options['check']:
            health = gateway.health_check()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Доступ подтверждён: {health['title']} ({len(health['sheets'])} листов)."
                )
            )
        if options['references']:
            result = sync_reference_data(gateway=gateway)
            self.stdout.write(self.style.SUCCESS(f"Справочники: {result}."))
        if options['pending']:
            result = sync_pending_submissions(limit=max(options['limit'], 1), gateway=gateway)
            self.stdout.write(self.style.SUCCESS(f"Очередь анкет: {result}."))
        if options['import_public']:
            result = import_public_client_statuses(limit=max(options['limit'], 1), gateway=gateway)
            self.stdout.write(self.style.SUCCESS(f"Публичные статусы: {result}."))
        if options['submission']:
            result = sync_submission(options['submission'], gateway=gateway)
            self.stdout.write(self.style.SUCCESS(f"Анкета: {result}."))
