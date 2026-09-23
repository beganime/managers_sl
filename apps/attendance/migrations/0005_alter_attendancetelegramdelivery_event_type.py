from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0004_attendancetelegramdelivery_target_chat_id_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendancetelegramdelivery',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('arrival', 'Приход'),
                    ('departure', 'Уход'),
                    ('auto_close', 'Автоматическое закрытие'),
                    ('missed', 'Неявка'),
                    ('weekly_summary', 'Недельный отчёт'),
                    ('start_reminder', 'Напоминание о начале дня'),
                    ('close_reminder', 'Напоминание о завершении дня'),
                    ('after_hours', 'Активность после рабочего дня'),
                ],
                db_index=True,
                max_length=32,
                verbose_name='Тип события',
            ),
        ),
    ]
