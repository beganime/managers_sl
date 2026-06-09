from django.db import migrations


def drop_programfee_valid_dates(apps, schema_editor):
    ProgramFee = apps.get_model('education', 'ProgramFee')
    table_name = ProgramFee._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    for field_name in ('valid_from', 'valid_to'):
        field = ProgramFee._meta.get_field(field_name)
        if field.column in existing_columns:
            schema_editor.remove_field(ProgramFee, field)


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(drop_programfee_valid_dates, migrations.RunPython.noop),
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
