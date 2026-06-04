from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE education_programfee DROP COLUMN IF EXISTS valid_from CASCADE;'
                        'ALTER TABLE education_programfee DROP COLUMN IF EXISTS valid_to CASCADE;'
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='programfee',
                    name='valid_from',
                ),
                migrations.RemoveField(
                    model_name='programfee',
                    name='valid_to',
                ),
            ],
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
