# Generated manually to sync leads.Lead database schema with the current model.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leads', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lead',
            name='direction',
            field=models.CharField(
                blank=True,
                choices=[
                    ('admission', 'Поступление'),
                    ('translation', 'Переводы'),
                    ('umrah', 'Умра/Хадж'),
                    ('visa', 'Виза'),
                    ('tickets', 'Билеты'),
                    ('tours', 'Туры в Туркменистан'),
                    ('work_visa', 'Рабочие визы'),
                ],
                max_length=50,
                verbose_name='Направление',
            ),
        ),
        migrations.AddField(
            model_name='lead',
            name='student_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='ФИО студента'),
        ),
        migrations.AddField(
            model_name='lead',
            name='parent_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='ФИО родителя'),
        ),
        migrations.AddField(
            model_name='lead',
            name='has_passport',
            field=models.CharField(blank=True, max_length=50, verbose_name='Наличие паспорта'),
        ),
        migrations.AddField(
            model_name='lead',
            name='passport_expiry',
            field=models.DateField(blank=True, null=True, verbose_name='Срок действия паспорта'),
        ),
        migrations.AddField(
            model_name='lead',
            name='travel_month',
            field=models.CharField(blank=True, max_length=50, verbose_name='Месяц поездки'),
        ),
        migrations.AddField(
            model_name='lead',
            name='travel_date',
            field=models.DateField(blank=True, null=True, verbose_name='Дата поездки'),
        ),
        migrations.AddField(
            model_name='lead',
            name='departure_city',
            field=models.CharField(blank=True, max_length=100, verbose_name='Город вылета'),
        ),
        migrations.AddField(
            model_name='lead',
            name='arrival_city',
            field=models.CharField(blank=True, max_length=100, verbose_name='Город прибытия'),
        ),
        migrations.AddField(
            model_name='lead',
            name='luggage',
            field=models.CharField(blank=True, max_length=100, verbose_name='Багаж'),
        ),
        migrations.AddField(
            model_name='lead',
            name='current_education',
            field=models.CharField(blank=True, max_length=255, verbose_name='Текущее образование'),
        ),
        migrations.AddField(
            model_name='lead',
            name='current_university',
            field=models.CharField(blank=True, max_length=255, verbose_name='Текущий университет'),
        ),
        migrations.AddField(
            model_name='lead',
            name='current_country',
            field=models.CharField(blank=True, max_length=100, verbose_name='Текущая страна'),
        ),
        migrations.AddField(
            model_name='lead',
            name='submitter_ip',
            field=models.GenericIPAddressField(blank=True, db_index=True, null=True, verbose_name='IP отправителя'),
        ),
        migrations.AddField(
            model_name='lead',
            name='submitter_user_agent',
            field=models.TextField(blank=True, default='', verbose_name='User-Agent отправителя'),
        ),
        migrations.AddField(
            model_name='lead',
            name='submitter_referer',
            field=models.URLField(blank=True, default='', max_length=1000, verbose_name='Referer'),
        ),
        migrations.AddField(
            model_name='lead',
            name='submitter_origin',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Origin'),
        ),
        migrations.AddField(
            model_name='lead',
            name='submitter_host',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Host'),
        ),
        migrations.AddField(
            model_name='lead',
            name='manager',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_leads',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Менеджер',
            ),
        ),
        migrations.AddField(
            model_name='lead',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
