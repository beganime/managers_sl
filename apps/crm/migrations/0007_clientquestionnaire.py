import apps.crm.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0006_mobile_client_documents'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientQuestionnaire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создано')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлено')),
                ('mobile_questionnaire_id', models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Mobile questionnaire ID')),
                ('external_mobile_user_id', models.PositiveIntegerField(blank=True, db_index=True, null=True, verbose_name='Mobile user ID')),
                ('source', models.CharField(blank=True, default='students_life_mobile_app', max_length=80, verbose_name='Источник')),
                ('status', models.CharField(choices=[('draft', 'Не заполнена'), ('submitted', 'Заполнена'), ('updated', 'Обновлена')], db_index=True, default='draft', max_length=20, verbose_name='Статус анкеты')),
                ('full_name', models.CharField(blank=True, max_length=255, verbose_name='ФИО')),
                ('phone', models.CharField(blank=True, max_length=80, verbose_name='Телефон')),
                ('email', models.EmailField(blank=True, max_length=254, null=True, verbose_name='Email')),
                ('citizenship', models.CharField(blank=True, max_length=120, verbose_name='Гражданство')),
                ('desired_program', models.CharField(blank=True, max_length=255, verbose_name='Желаемая программа / Вуз')),
                ('desired_country', models.CharField(blank=True, max_length=120, verbose_name='Желаемая страна')),
                ('desired_city', models.CharField(blank=True, max_length=120, verbose_name='Желаемый город')),
                ('face_photo_url', models.URLField(blank=True, max_length=1000, verbose_name='Фото абитуриента')),
                ('data', models.JSONField(blank=True, default=dict, verbose_name='Данные анкеты')),
                ('generated_file', models.FileField(blank=True, null=True, upload_to=apps.crm.models.client_questionnaire_document_upload_to, verbose_name='Сгенерированный документ')),
                ('submitted_at', models.DateTimeField(blank=True, null=True, verbose_name='Дата заполнения')),
                ('last_synced_at', models.DateTimeField(blank=True, null=True, verbose_name='Последняя синхронизация')),
                ('client', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='questionnaire', to='crm.client', verbose_name='Клиент')),
            ],
            options={
                'verbose_name': 'Анкета клиента',
                'verbose_name_plural': 'Анкеты клиентов',
                'ordering': ['-updated_at'],
                'indexes': [
                    models.Index(fields=['status', 'updated_at'], name='crm_clientq_status_7a6a3f_idx'),
                    models.Index(fields=['external_mobile_user_id'], name='crm_clientq_externa_0d0c67_idx'),
                ],
            },
        ),
    ]
