import django.utils.timezone
from django.db import migrations, models
from django.db.models import F


def copy_created_time(apps, schema_editor):
    EmployeeMood = apps.get_model('portal', 'EmployeeMood')
    EmployeeMood.objects.update(updated_at=F('created_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0002_employeemood'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeemood',
            name='updated_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(copy_created_time, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='employeemood',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
