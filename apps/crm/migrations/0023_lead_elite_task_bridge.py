from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('crm', '0022_client_is_public'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='lead',
            name='processed_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Дата обработки'),
        ),
        migrations.AddField(
            model_name='lead',
            name='processed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_crm_leads', to=settings.AUTH_USER_MODEL, verbose_name='Кто отметил обработанной'),
        ),
        migrations.CreateModel(
            name='LeadEliteTaskState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('status', models.CharField(choices=[('pending', 'Ожидает отправки'), ('sent', 'Отправлено'), ('failed', 'Ошибка')], db_index=True, default='pending', max_length=16)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('elite_task_lead_id', models.CharField(blank=True, max_length=80)),
                ('last_error', models.CharField(blank=True, max_length=500)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('lead', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='elite_task_state', to='crm.lead')),
            ],
            options={
                'verbose_name': 'Синхронизация лида с Elite Task',
                'verbose_name_plural': 'Синхронизация лидов с Elite Task',
            },
        ),
    ]
