from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='programfee',
            name='valid_from',
        ),
        migrations.RemoveField(
            model_name='programfee',
            name='valid_to',
        ),
        migrations.AlterModelOptions(
            name='programfee',
            options={
                'ordering': ['program__university__name', 'program__name', '-created_at'],
                'verbose_name': 'Стоимость программы',
                'verbose_name_plural': 'Стоимость программ',
            },
        ),
    ]
