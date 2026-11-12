from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0005_employeeprofile_attendance_required'),
    ]

    operations = [
        migrations.AddField(
            model_name='employeeprofile',
            name='attendance_exempt',
            field=models.BooleanField(
                default=False,
                verbose_name='Не учитывать рабочий день (СММ, помощники, руководители, стажёры)',
            ),
        ),
    ]
