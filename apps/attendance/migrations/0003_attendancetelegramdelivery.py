from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('attendance', '0002_alter_workday_status'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceTelegramDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('event_key', models.CharField(max_length=190, unique=True, verbose_name='Ключ события')),
                ('event_type', models.CharField(choices=[('arrival', 'Приход'), ('departure', 'Уход'), ('auto_close', 'Автоматическое закрытие'), ('missed', 'Неявка'), ('weekly_summary', 'Недельный отчёт')], db_index=True, max_length=32, verbose_name='Тип события')),
                ('message', models.TextField(verbose_name='Сообщение')),
                ('status', models.CharField(choices=[('pending', 'Ожидает'), ('sent', 'Отправлено'), ('failed', 'Ошибка')], db_index=True, default='pending', max_length=16, verbose_name='Статус')),
                ('attempts', models.PositiveSmallIntegerField(default=0, verbose_name='Попытки')),
                ('last_error', models.CharField(blank=True, max_length=255, verbose_name='Последняя ошибка')),
                ('sent_at', models.DateTimeField(blank=True, null=True, verbose_name='Отправлено')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_telegram_deliveries', to='organizations.company')),
                ('employee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendance_telegram_deliveries', to=settings.AUTH_USER_MODEL)),
                ('office', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='attendance_telegram_deliveries', to='organizations.office')),
                ('workday', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='telegram_deliveries', to='attendance.workday')),
            ],
            options={
                'verbose_name': 'Telegram-событие рабочего дня',
                'verbose_name_plural': 'Telegram-события рабочего дня',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='attendancetelegramdelivery',
            index=models.Index(fields=['status', 'created_at'], name='attendance__status_98de3f_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancetelegramdelivery',
            index=models.Index(fields=['company', 'event_type', 'created_at'], name='attendance__company_8cc142_idx'),
        ),
    ]
