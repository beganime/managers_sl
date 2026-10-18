from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0013_client_funding_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='client',
            name='funding_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('government', 'Государственная линия'),
                    ('budget', 'Бюджет'),
                    ('contract', 'Контракт'),
                    ('medical', 'Медик'),
                ],
                max_length=20,
                verbose_name='Форма поступления',
            ),
        ),
    ]
