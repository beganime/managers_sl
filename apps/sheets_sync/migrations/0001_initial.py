from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SheetRowBinding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('spreadsheet_id', models.CharField(db_index=True, max_length=160, verbose_name='ID книги')),
                ('sheet_name', models.CharField(max_length=100, verbose_name='Лист')),
                ('entity_type', models.CharField(choices=[('client', 'Клиент'), ('application', 'Заявка в ВУЗ'), ('finance', 'Финансовая операция'), ('exam', 'Экзамен')], max_length=32, verbose_name='Тип сущности')),
                ('object_ref', models.CharField(max_length=100, verbose_name='ID объекта ManagerSL')),
                ('sl_id', models.CharField(db_index=True, max_length=32, verbose_name='SL-ID')),
                ('row_number', models.PositiveIntegerField(verbose_name='Номер строки')),
                ('sync_version', models.PositiveIntegerField(default=1, verbose_name='Версия синхронизации')),
                ('row_hash', models.CharField(blank=True, max_length=64, verbose_name='Хеш синхронизированных данных')),
                ('last_synced_at', models.DateTimeField(blank=True, null=True, verbose_name='Последняя синхронизация')),
            ],
            options={
                'verbose_name': 'Связь со строкой Google Sheets',
                'verbose_name_plural': 'Связи со строками Google Sheets',
                'ordering': ['sheet_name', 'row_number'],
            },
        ),
        migrations.CreateModel(
            name='SheetSyncRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('kind', models.CharField(choices=[('references', 'Справочники'), ('submission', 'Анкета'), ('pending', 'Очередь анкет')], max_length=24, verbose_name='Тип запуска')),
                ('status', models.CharField(choices=[('running', 'Выполняется'), ('success', 'Успешно'), ('failed', 'Ошибка'), ('skipped', 'Пропущено')], default='running', max_length=16, verbose_name='Статус')),
                ('object_ref', models.CharField(blank=True, max_length=100, verbose_name='Связанный объект')),
                ('processed', models.PositiveIntegerField(default=0, verbose_name='Обработано')),
                ('failed', models.PositiveIntegerField(default=0, verbose_name='Ошибок')),
                ('error', models.TextField(blank=True, verbose_name='Ошибка')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='Завершено')),
            ],
            options={
                'verbose_name': 'Запуск синхронизации Google Sheets',
                'verbose_name_plural': 'Запуски синхронизации Google Sheets',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='sheetrowbinding',
            constraint=models.UniqueConstraint(fields=('spreadsheet_id', 'sheet_name', 'sl_id'), name='uniq_sheet_row_by_sl_id'),
        ),
        migrations.AddConstraint(
            model_name='sheetrowbinding',
            constraint=models.UniqueConstraint(fields=('spreadsheet_id', 'sheet_name', 'entity_type', 'object_ref'), name='uniq_sheet_row_by_object'),
        ),
        migrations.AddIndex(
            model_name='sheetrowbinding',
            index=models.Index(fields=['entity_type', 'object_ref'], name='sheets_sync_entity__9d1d17_idx'),
        ),
        migrations.AddIndex(
            model_name='sheetrowbinding',
            index=models.Index(fields=['spreadsheet_id', 'sheet_name', 'row_number'], name='sheets_sync_spreads_7f32c9_idx'),
        ),
        migrations.AddIndex(
            model_name='sheetsyncrun',
            index=models.Index(fields=['kind', 'status', 'created_at'], name='sheets_sync_kind_eb6dc5_idx'),
        ),
    ]
