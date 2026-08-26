from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('sheets_sync', '0002_clientadmissionsnapshot'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sheetsyncrun',
            name='kind',
            field=models.CharField(
                choices=[
                    ('references', 'Справочники'),
                    ('submission', 'Анкета'),
                    ('pending', 'Очередь анкет'),
                    ('public_status', 'Статусы клиентов'),
                    ('onboarding_inbox', 'Входящие анкеты'),
                    ('onboarding_decisions', 'Решения по анкетам'),
                ],
                max_length=24,
                verbose_name='Тип запуска',
            ),
        ),
    ]
