from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('client_onboarding', '0003_clientprovisioningstep'),
    ]

    operations = [
        migrations.AddField(
            model_name='onboardingsubmission',
            name='stage',
            field=models.CharField(
                choices=[('express', 'Экспресс-заявка'), ('full', 'Полная анкета')],
                db_index=True,
                default='full',
                max_length=16,
                verbose_name='Этап заявки',
            ),
        ),
    ]
