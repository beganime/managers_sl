# Generated manually for ERP rebuild Sprint 1

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EmployeeRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Updated at')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Active')),
                ('code', models.SlugField(max_length=64, unique=True, verbose_name='Role code')),
                ('name', models.CharField(max_length=150, verbose_name='Role name')),
                ('role_type', models.CharField(choices=[('company_owner', 'Company owner'), ('office_director', 'Office director'), ('manager', 'Manager'), ('accountant', 'Accountant'), ('hr', 'HR'), ('viewer', 'Viewer')], db_index=True, max_length=32, verbose_name='Role type')),
                ('description', models.TextField(blank=True, verbose_name='Description')),
            ],
            options={'verbose_name': 'Employee role', 'verbose_name_plural': 'Employee roles', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='EmployeeProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Updated at')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='Active')),
                ('work_status', models.CharField(choices=[('working', 'Working'), ('vacation', 'Vacation'), ('sick', 'Sick'), ('fired', 'Fired'), ('paused', 'Paused')], default='working', max_length=32, verbose_name='Work status')),
                ('hire_date', models.DateField(default=django.utils.timezone.localdate, verbose_name='Hire date')),
                ('fired_date', models.DateField(blank=True, null=True, verbose_name='End date')),
                ('salary_type', models.CharField(choices=[('fixed', 'Fixed'), ('commission', 'Commission'), ('mixed', 'Fixed plus commission')], default='mixed', max_length=32, verbose_name='Salary type')),
                ('fixed_salary', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=10, verbose_name='Fixed salary USD')),
                ('commission_percent', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5, verbose_name='Commission percent')),
                ('rating', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=7, verbose_name='Rating')),
                ('notes', models.TextField(blank=True, verbose_name='Notes')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='employees', to='organizations.company', verbose_name='Company')),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='organizations.department', verbose_name='Department')),
                ('office', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='organizations.office', verbose_name='Office')),
                ('position', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='organizations.position', verbose_name='Position')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='employees', to='employees.employeerole', verbose_name='Role')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='employee_profile', to=settings.AUTH_USER_MODEL, verbose_name='User')),
            ],
            options={'verbose_name': 'Employee profile', 'verbose_name_plural': 'Employee profiles', 'ordering': ['company__name', 'office__city', 'user__first_name', 'user__last_name']},
        ),
        migrations.CreateModel(
            name='EmployeeAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Updated at')),
                ('can_see_all_company', models.BooleanField(default=False, verbose_name='See all company')),
                ('can_see_all_office', models.BooleanField(default=False, verbose_name='See all office')),
                ('can_manage_finance', models.BooleanField(default=False, verbose_name='Manage finance')),
                ('can_manage_hr', models.BooleanField(default=False, verbose_name='Manage HR')),
                ('can_manage_documents', models.BooleanField(default=False, verbose_name='Manage documents')),
                ('can_manage_catalog', models.BooleanField(default=False, verbose_name='Manage catalog')),
                ('can_be_in_leaderboard', models.BooleanField(default=True, verbose_name='Show in leaderboard')),
                ('employee', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='access', to='employees.employeeprofile', verbose_name='Employee')),
            ],
            options={'verbose_name': 'Employee access', 'verbose_name_plural': 'Employee access'},
        ),
        migrations.CreateModel(
            name='EmployeeRating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Updated at')),
                ('date', models.DateField(db_index=True, default=django.utils.timezone.localdate, verbose_name='Date')),
                ('score', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=7, verbose_name='Score')),
                ('source', models.CharField(blank=True, max_length=100, verbose_name='Source')),
                ('comment', models.TextField(blank=True, verbose_name='Comment')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rating_logs', to='employees.employeeprofile', verbose_name='Employee')),
            ],
            options={'verbose_name': 'Employee rating log', 'verbose_name_plural': 'Employee rating logs', 'ordering': ['-date', '-created_at']},
        ),
    ]
