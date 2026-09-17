# Generated manually for the canonical ExamSL integration.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('crm', '0018_clientfilereviewevent_clientfileversion_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ApplicationExam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('subject', models.CharField(max_length=255, verbose_name='Экзамен / предмет')),
                ('scheduled_at', models.DateTimeField(db_index=True, verbose_name='Дата и время')),
                ('timezone', models.CharField(default='Asia/Ashgabat', max_length=64, verbose_name='Часовой пояс')),
                ('join_url', models.URLField(blank=True, max_length=1000, verbose_name='Ссылка')),
                ('login', models.CharField(blank=True, max_length=255, verbose_name='Логин')),
                ('secret_ciphertext', models.TextField(blank=True, verbose_name='Зашифрованный пароль')),
                ('status', models.CharField(choices=[('SCHEDULED', 'Назначен'), ('CONFIRMED', 'Подтверждён'), ('COMPLETED', 'Пройден'), ('PASSED', 'Сдан'), ('FAILED', 'Не сдан'), ('CANCELLED', 'Отменён')], db_index=True, default='SCHEDULED', max_length=20)),
                ('result', models.CharField(blank=True, max_length=255, verbose_name='Результат')),
                ('score', models.CharField(blank=True, max_length=80, verbose_name='Балл')),
                ('retake_at', models.DateTimeField(blank=True, null=True, verbose_name='Пересдача')),
                ('comment', models.CharField(blank=True, max_length=1000, verbose_name='Комментарий')),
                ('source_service', models.CharField(default='manager_sl', max_length=80)),
                ('source_id', models.CharField(max_length=120)),
                ('source_version', models.PositiveIntegerField(default=1)),
                ('client_acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('application', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='exams', to='crm.application', verbose_name='Заявка в университет')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_application_exams', to=settings.AUTH_USER_MODEL, verbose_name='Создал')),
                ('responsible', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='responsible_application_exams', to=settings.AUTH_USER_MODEL, verbose_name='Ответственный')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='application_exams', to='crm.client', verbose_name='Студент')),
            ],
            options={'ordering': ['scheduled_at', 'created_at']},
        ),
        migrations.CreateModel(
            name='ApplicationExamEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('event_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('action', models.CharField(db_index=True, max_length=80)),
                ('source_service', models.CharField(default='manager_sl', max_length=80)),
                ('old_data', models.JSONField(blank=True, default=dict)),
                ('new_data', models.JSONField(blank=True, default=dict)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='application_exam_events', to=settings.AUTH_USER_MODEL)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='events', to='crm.applicationexam')),
            ],
            options={'ordering': ['-created_at'], 'default_permissions': ('add', 'view')},
        ),
        migrations.AddConstraint(
            model_name='applicationexam',
            constraint=models.UniqueConstraint(fields=('source_service', 'source_id'), name='unique_exam_source_record'),
        ),
        migrations.AddIndex(model_name='applicationexam', index=models.Index(fields=['application', 'scheduled_at'], name='crm_applica_applica_b14a52_idx')),
        migrations.AddIndex(model_name='applicationexam', index=models.Index(fields=['student', 'scheduled_at'], name='crm_applica_student_cfeb3a_idx')),
        migrations.AddIndex(model_name='applicationexam', index=models.Index(fields=['status', 'scheduled_at'], name='crm_applica_status_76c147_idx')),
        migrations.AddIndex(model_name='applicationexamevent', index=models.Index(fields=['exam', 'created_at'], name='crm_applica_exam_id_a820ab_idx')),
    ]
