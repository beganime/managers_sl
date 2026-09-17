from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0005_lead_api_source_lead_archive_reason_lead_archived_at_and_more'),
        ('sheets_sync', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientAdmissionSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('current_status', models.CharField(blank=True, max_length=255, verbose_name='Текущий статус')),
                ('invitation_city', models.CharField(blank=True, max_length=255, verbose_name='Город приглашения')),
                ('meeting', models.CharField(blank=True, max_length=100, verbose_name='Встреча')),
                ('current_location', models.CharField(blank=True, max_length=255, verbose_name='Текущее местонахождение')),
                ('spreadsheet_id', models.CharField(max_length=160, verbose_name='ID книги')),
                ('sheet_name', models.CharField(max_length=100, verbose_name='Лист')),
                ('row_number', models.PositiveIntegerField(verbose_name='Номер строки')),
                ('source_hash', models.CharField(max_length=64, verbose_name='Хеш исходных данных')),
                ('source_updated_value', models.CharField(blank=True, max_length=100, verbose_name='Значение «Обновлено»')),
                ('last_imported_at', models.DateTimeField(verbose_name='Последний импорт')),
                ('client', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='admission_snapshot', to='crm.client', verbose_name='Клиент')),
            ],
            options={
                'verbose_name': 'Публичный статус поступления',
                'verbose_name_plural': 'Публичные статусы поступления',
                'ordering': ['client__sl_id'],
            },
        ),
        migrations.AlterField(
            model_name='sheetsyncrun',
            name='kind',
            field=models.CharField(choices=[('references', 'Справочники'), ('submission', 'Анкета'), ('pending', 'Очередь анкет'), ('public_status', 'Статусы клиентов')], max_length=24, verbose_name='Тип запуска'),
        ),
    ]
