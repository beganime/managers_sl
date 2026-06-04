from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0002_alter_employeeaccess_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeaccess',
            name='must_track_workday',
            field=models.BooleanField(default=True, verbose_name='Обязан отмечать рабочий день'),
        ),
    ]
