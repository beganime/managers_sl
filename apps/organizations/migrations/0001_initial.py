# Generated manually for ERP rebuild Sprint 1

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Активно')),
                ('name', models.CharField(db_index=True, max_length=255, verbose_name='Название компании')),
                ('legal_name', models.CharField(blank=True, max_length=255, verbose_name='Юридическое название')),
                ('registration_number', models.CharField(blank=True, max_length=100, verbose_name='ИНН / регистрационный номер')),
                ('country', models.CharField(default='Россия', max_length=100, verbose_name='Страна')),
                ('city', models.CharField(blank=True, max_length=100, verbose_name='Город')),
                ('address', models.CharField(blank=True, max_length=255, verbose_name='Адрес')),
                ('phone', models.CharField(blank=True, max_length=50, verbose_name='Телефон')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Email')),
                ('website', models.URLField(blank=True, verbose_name='Сайт')),
                ('logo', models.ImageField(blank=True, null=True, upload_to='erp/companies/logos/', verbose_name='Логотип')),
                ('stamp', models.ImageField(blank=True, null=True, upload_to='erp/companies/stamps/', verbose_name='Печать')),
                ('notes', models.TextField(blank=True, verbose_name='Заметки')),
                ('owner', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_erp_companies', to=settings.AUTH_USER_MODEL, verbose_name='Владелец / главный ответственный')),
            ],
            options={
                'verbose_name': 'Компания',
                'verbose_name_plural': 'Компании',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Активно')),
                ('sort_order', models.PositiveIntegerField(db_index=True, default=0, verbose_name='Порядок')),
                ('name', models.CharField(max_length=150, verbose_name='Название отдела')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='departments', to='organizations.company', verbose_name='Компания')),
            ],
            options={
                'verbose_name': 'Отдел',
                'verbose_name_plural': 'Отделы',
                'ordering': ['company__name', 'sort_order', 'name'],
                'unique_together': {('company', 'name')},
            },
        ),
        migrations.CreateModel(
            name='Office',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Активно')),
                ('name', models.CharField(max_length=255, verbose_name='Название офиса')),
                ('country', models.CharField(default='Россия', max_length=100, verbose_name='Страна')),
                ('city', models.CharField(db_index=True, max_length=100, verbose_name='Город')),
                ('address', models.CharField(blank=True, max_length=255, verbose_name='Адрес')),
                ('phone', models.CharField(blank=True, max_length=50, verbose_name='Телефон офиса')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='Email офиса')),
                ('timezone', models.CharField(default='Asia/Ashgabat', max_length=64, verbose_name='Часовой пояс')),
                ('notes', models.TextField(blank=True, verbose_name='Заметки')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offices', to='organizations.company', verbose_name='Компания')),
                ('director', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='directed_erp_offices', to=settings.AUTH_USER_MODEL, verbose_name='Руководитель офиса')),
            ],
            options={
                'verbose_name': 'Офис',
                'verbose_name_plural': 'Офисы',
                'ordering': ['company__name', 'city', 'name'],
                'unique_together': {('company', 'name', 'city')},
            },
        ),
        migrations.CreateModel(
            name='Position',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Активно')),
                ('sort_order', models.PositiveIntegerField(db_index=True, default=0, verbose_name='Порядок')),
                ('name', models.CharField(max_length=150, verbose_name='Должность')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='positions', to='organizations.company', verbose_name='Компания')),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='positions', to='organizations.department', verbose_name='Отдел')),
            ],
            options={
                'verbose_name': 'Должность',
                'verbose_name_plural': 'Должности',
                'ordering': ['company__name', 'department__name', 'sort_order', 'name'],
                'unique_together': {('company', 'department', 'name')},
            },
        ),
    ]
