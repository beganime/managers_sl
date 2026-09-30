from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('employees', '0004_employeeaccess_rating_priority_enabled_and_more')]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='attendance_required',
            field=models.BooleanField(default=False, verbose_name='Учитывать рабочий день при роли администратора'),
        ),
    ]
