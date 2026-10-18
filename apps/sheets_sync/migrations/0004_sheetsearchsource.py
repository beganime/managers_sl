from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sheets_sync', '0003_alter_sheetsyncrun_kind')]

    operations = [
        migrations.CreateModel(
            name='SheetSearchSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('title', models.CharField(max_length=160, verbose_name='Название книги')),
                ('spreadsheet_id', models.CharField(max_length=160, unique=True, verbose_name='ID Google Sheets')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Искать в этой книге')),
            ],
            options={
                'verbose_name': 'Источник поиска Google Sheets',
                'verbose_name_plural': 'Источники поиска Google Sheets',
                'ordering': ['title'],
            },
        ),
    ]
