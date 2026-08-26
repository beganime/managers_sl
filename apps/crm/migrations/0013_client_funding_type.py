from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('crm', '0012_client_academic_year_client_sl_id')]

    operations = [
        migrations.AddField(
            model_name='client',
            name='funding_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('government', 'Государственная линия'),
                    ('budget', 'Бюджет'),
                    ('contract', 'Контракт'),
                ],
                max_length=20,
                verbose_name='Форма поступления',
            ),
        ),
    ]
