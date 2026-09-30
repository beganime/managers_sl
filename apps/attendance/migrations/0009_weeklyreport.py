import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0008_telegram_topics_and_report_events'),
        ('organizations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WeeklyReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('period_start', models.DateField(db_index=True, verbose_name='Начало недели')),
                ('period_end', models.DateField(db_index=True, verbose_name='Конец недели')),
                ('work_done', models.TextField(max_length=4000, verbose_name='Что проделано за неделю')),
                ('remarks', models.TextField(blank=True, max_length=2000, verbose_name='Замечания')),
                ('next_week_plans', models.TextField(max_length=4000, verbose_name='Планы на следующую неделю')),
                ('improvement_ideas', models.TextField(blank=True, max_length=2000, verbose_name='Идеи для улучшения')),
                ('difficulties', models.TextField(blank=True, max_length=2000, verbose_name='Сложности')),
                ('needs', models.TextField(blank=True, max_length=2000, verbose_name='Что нужно')),
                ('waiting_for', models.TextField(blank=True, max_length=2000, verbose_name='От кого и чего ожидает')),
                ('information', models.TextField(blank=True, max_length=2000, verbose_name='Для информации, исключения')),
                ('generated_file', models.FileField(blank=True, upload_to='attendance/weekly/%Y/%m/')),
                ('disk_path', models.CharField(blank=True, max_length=500)),
                ('disk_archived_at', models.DateTimeField(blank=True, null=True)),
                ('telegram_sent_at', models.DateTimeField(blank=True, null=True)),
                ('telegram_error', models.CharField(blank=True, max_length=255)),
                ('submitted_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('expires_at', models.DateTimeField()),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='weekly_employee_reports', to='organizations.company')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='weekly_employee_reports', to=settings.AUTH_USER_MODEL)),
                ('office', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='weekly_employee_reports', to='organizations.office')),
            ],
            options={
                'verbose_name': 'Еженедельный отчёт сотрудника',
                'verbose_name_plural': 'Еженедельные отчёты сотрудников',
                'ordering': ['-period_end', '-submitted_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='weeklyreport',
            constraint=models.UniqueConstraint(fields=('company', 'employee', 'period_start'), name='attendance_weekly_report_employee_period_uniq'),
        ),
        migrations.AddIndex(model_name='weeklyreport', index=models.Index(fields=['company', 'period_end'], name='attendance__company_a4ac02_idx')),
        migrations.AddIndex(model_name='weeklyreport', index=models.Index(fields=['employee', 'period_end'], name='attendance__employe_c0b4d9_idx')),
        migrations.AddIndex(model_name='weeklyreport', index=models.Index(fields=['expires_at'], name='attendance__expires_b9510e_idx')),
    ]
