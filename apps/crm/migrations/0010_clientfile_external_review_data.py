from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0009_clientquestionnaire_status_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientfile',
            name='external_review_data',
            field=models.JSONField(blank=True, default=dict, verbose_name='Ответ проверки Student’s Life'),
        ),
    ]
