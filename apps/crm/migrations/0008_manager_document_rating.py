from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0007_clientquestionnaire'),
        ('employees', '0004_employeeaccess_rating_priority_enabled_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientquestionnaire',
            name='status',
            field=models.CharField(choices=[('draft', 'Не заполнена'), ('completed', 'Заполнена'), ('submitted', 'Заполнена'), ('updated', 'Обновлена')], db_index=True, default='draft', max_length=20, verbose_name='Статус анкеты'),
        ),
        migrations.CreateModel(
            name='ManagerDocumentPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Активно')),
                ('period_type', models.CharField(choices=[('day', 'День'), ('week', 'Неделя'), ('month', 'Месяц'), ('custom', 'Произвольный период')], default='month', max_length=16, verbose_name='Период')),
                ('start_date', models.DateField(db_index=True, verbose_name='Дата начала')),
                ('end_date', models.DateField(db_index=True, verbose_name='Дата окончания')),
                ('target_clients', models.PositiveIntegerField(default=0, verbose_name='План по загруженным клиентам')),
                ('admin_comment', models.TextField(blank=True, verbose_name='Комментарий администратора')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_plans', to='employees.employeeprofile', verbose_name='Менеджер')),
            ],
            options={
                'verbose_name': 'План менеджера по документам',
                'verbose_name_plural': 'Планы менеджеров по документам',
                'ordering': ['-start_date', 'employee__user__first_name'],
            },
        ),
        migrations.CreateModel(
            name='ManagerDocumentCredit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('event_type', models.CharField(choices=[('uploaded_client_documents', 'Документы клиента загружены')], db_index=True, default='uploaded_client_documents', max_length=64, verbose_name='Тип события')),
                ('period_start', models.DateField(db_index=True, verbose_name='Начало периода')),
                ('period_end', models.DateField(db_index=True, verbose_name='Конец периода')),
                ('credited_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='Дата зачёта')),
                ('comment', models.TextField(blank=True, verbose_name='Комментарий')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_manager_credits', to='crm.client', verbose_name='Клиент')),
                ('credited_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='document_credits_created', to=settings.AUTH_USER_MODEL, verbose_name='Кто засчитал')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='document_credits', to='employees.employeeprofile', verbose_name='Менеджер')),
                ('plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='credits', to='crm.managerdocumentplan', verbose_name='План')),
            ],
            options={
                'verbose_name': 'Зачёт загруженного клиента',
                'verbose_name_plural': 'Зачёты загруженных клиентов',
                'ordering': ['-credited_at'],
            },
        ),
        migrations.AddIndex(
            model_name='managerdocumentplan',
            index=models.Index(fields=['employee', 'start_date', 'end_date', 'is_active'], name='crm_mdocplan_emp_period_idx'),
        ),
        migrations.AddIndex(
            model_name='managerdocumentcredit',
            index=models.Index(fields=['employee', 'period_start', 'period_end'], name='crm_mdoccredit_emp_period_idx'),
        ),
        migrations.AddIndex(
            model_name='managerdocumentcredit',
            index=models.Index(fields=['client', 'event_type'], name='crm_mdoccredit_client_idx'),
        ),
        migrations.AddConstraint(
            model_name='managerdocumentcredit',
            constraint=models.UniqueConstraint(fields=('employee', 'client', 'event_type', 'period_start', 'period_end'), name='uniq_manager_client_document_credit_period'),
        ),
    ]
