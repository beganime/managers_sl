from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0007_alter_attendancetelegramdelivery_event_type')]

    operations = [
        migrations.AddField(
            model_name='attendancetelegramdelivery',
            name='target_message_thread_id',
            field=models.PositiveBigIntegerField(blank=True, null=True, verbose_name='Тема Telegram'),
        ),
        migrations.AlterField(
            model_name='attendancetelegramdelivery',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('arrival', 'Приход'), ('departure', 'Уход'),
                    ('auto_close', 'Автоматическое закрытие'), ('missed', 'Неявка'),
                    ('daily_summary', 'Ежедневная сводка'), ('weekly_summary', 'Недельный отчёт'),
                    ('start_reminder', 'Напоминание о начале дня'),
                    ('close_reminder', 'Напоминание о завершении дня'),
                    ('report_reminder', 'Напоминание об отчёте'),
                    ('after_hours', 'Активность после рабочего дня'),
                    ('admin_message', 'Сообщение руководителя'),
                    ('report_submitted', 'Отчёт сотрудника'),
                ],
                db_index=True,
                max_length=32,
                verbose_name='Тип события',
            ),
        ),
        migrations.CreateModel(
            name='AttendanceTelegramTopic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('chat_id', models.BigIntegerField(db_index=True, verbose_name='Telegram group ID')),
                ('topic_type', models.CharField(choices=[('daily', 'Итоги дня'), ('reports', 'Отчёты'), ('absent', 'Не пришедшие'), ('time', 'Время')], max_length=16, verbose_name='Назначение темы')),
                ('message_thread_id', models.PositiveBigIntegerField(verbose_name='Telegram topic ID')),
                ('title', models.CharField(blank=True, max_length=128, verbose_name='Название темы')),
                ('configured_by_telegram_user_id', models.BigIntegerField(blank=True, null=True, verbose_name='Кто настроил')),
            ],
            options={
                'verbose_name': 'Тема Telegram для учёта',
                'verbose_name_plural': 'Темы Telegram для учёта',
                'constraints': [
                    models.UniqueConstraint(fields=('chat_id', 'topic_type'), name='attendance_topic_chat_type_uniq'),
                    models.UniqueConstraint(fields=('chat_id', 'message_thread_id'), name='attendance_topic_chat_thread_uniq'),
                ],
            },
        ),
    ]
