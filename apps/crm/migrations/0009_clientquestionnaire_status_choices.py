# Generated manually for Student's Life questionnaire statuses.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0008_manager_document_rating'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientquestionnaire',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Не заполнена'),
                    ('completed', 'Заполнена'),
                    ('submitted', 'Отправлена на проверку'),
                    ('approved', 'Принята'),
                    ('rejected', 'Отклонена'),
                    ('updated', 'Обновлена'),
                ],
                db_index=True,
                default='draft',
                max_length=20,
                verbose_name='Статус анкеты',
            ),
        ),
    ]
