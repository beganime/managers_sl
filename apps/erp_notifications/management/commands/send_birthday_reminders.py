from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date

from apps.erp_notifications.services import send_birthday_reminders_for_date


class Command(BaseCommand):
    help = 'Отправляет уведомления за день до дня рождения сотрудников.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            dest='date',
            default='',
            help='Дата напоминания в формате YYYY-MM-DD. По умолчанию сегодня в timezone проекта.',
        )

    def handle(self, *args, **options):
        reminder_date = parse_date(options.get('date') or '') if options.get('date') else None
        result = send_birthday_reminders_for_date(today=reminder_date)
        self.stdout.write(self.style.SUCCESS(
            'Birthday reminders: '
            f'created={result["created"]}, '
            f'batches={result["batches"]}, '
            f'skipped={result["skipped"]}, '
            f'birthday_people={result["birthday_people"]}'
        ))
