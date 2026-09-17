from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


USD_TO_TMT = Decimal('19.600000')


def backfill_finance_data(apps, schema_editor):
    Currency = apps.get_model('education', 'Currency')
    Deal = apps.get_model('finance', 'Deal')
    Payment = apps.get_model('finance', 'Payment')
    Expense = apps.get_model('finance', 'Expense')
    Income = apps.get_model('finance', 'Income')
    Transaction = apps.get_model('finance', 'Transaction')

    currency_codes = dict(Currency.objects.values_list('id', 'code'))

    def tmt_amount(item):
        code = str(currency_codes.get(item.currency_id) or '').upper()
        if code == 'TMT':
            return (item.amount or Decimal('0.00')).quantize(Decimal('0.01'))
        return ((item.amount_usd or Decimal('0.00')) * USD_TO_TMT).quantize(Decimal('0.01'))

    for model in (Payment, Expense, Income, Transaction):
        for item in model.objects.all().iterator(chunk_size=500):
            model.objects.filter(pk=item.pk).update(amount_tmt=tmt_amount(item))

    for deal in Deal.objects.filter(contract_number__isnull=True).iterator(chunk_size=500):
        year = deal.contract_date.year if deal.contract_date else django.utils.timezone.localdate().year
        Deal.objects.filter(pk=deal.pk).update(contract_number=f'SL-DOG-{year}-{deal.pk:05d}')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('education', '0001_initial'),
        ('finance', '0003_payment_expense_proof_files'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinanceSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('usd_to_tmt', models.DecimalField(decimal_places=6, default=Decimal('19.600000'), help_text='Сколько TMT составляет 1 USD. По умолчанию: 19.6.', max_digits=14, verbose_name='Курс USD → TMT')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Изменено')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='updated_finance_settings', to=settings.AUTH_USER_MODEL, verbose_name='Кто изменил')),
            ],
            options={
                'verbose_name': 'Настройки финансов',
                'verbose_name_plural': 'Настройки финансов',
            },
        ),
        migrations.CreateModel(
            name='EmployeeBalance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('balance_tmt', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16, verbose_name='Баланс сотрудника, TMT')),
                ('employee', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='finance_balance', to=settings.AUTH_USER_MODEL, verbose_name='Сотрудник')),
                ('office', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employee_balances', to='organizations.office', verbose_name='Офис')),
            ],
            options={
                'verbose_name': 'Баланс сотрудника',
                'verbose_name_plural': 'Балансы сотрудников',
                'ordering': ['employee__first_name', 'employee__last_name', 'employee__email'],
            },
        ),
        migrations.AddField(
            model_name='deal',
            name='contract_date',
            field=models.DateField(db_index=True, default=django.utils.timezone.localdate, verbose_name='Дата договора'),
        ),
        migrations.AddField(
            model_name='deal',
            name='contract_number',
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True, unique=True, verbose_name='Номер договора'),
        ),
        migrations.AddField(
            model_name='deal',
            name='disk_folder',
            field=models.CharField(blank=True, max_length=500, verbose_name='Папка договора в DiskSL'),
        ),
        migrations.AddField(
            model_name='deal',
            name='payment_due_date',
            field=models.DateField(blank=True, db_index=True, null=True, verbose_name='Срок полной оплаты'),
        ),
        migrations.AddField(
            model_name='income',
            name='amount_tmt',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16, verbose_name='Сумма, TMT'),
        ),
        migrations.AddField(
            model_name='expense',
            name='amount_tmt',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16, verbose_name='Сумма, TMT'),
        ),
        migrations.AddField(
            model_name='payment',
            name='amount_tmt',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16, verbose_name='Сумма, TMT'),
        ),
        migrations.AddField(
            model_name='transaction',
            name='amount_tmt',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16, verbose_name='Сумма, TMT'),
        ),
        migrations.CreateModel(
            name='DealAdditionalService',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Дата создания')),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Дата обновления')),
                ('title', models.CharField(max_length=255, verbose_name='Дополнительная услуга')),
                ('amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14, verbose_name='Сумма')),
                ('exchange_rate', models.DecimalField(decimal_places=6, default=Decimal('1.000000'), max_digits=14, verbose_name='Курс к USD')),
                ('amount_usd', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14, verbose_name='Сумма, USD')),
                ('comment', models.CharField(blank=True, max_length=1000, verbose_name='Комментарий')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_deal_additional_services', to=settings.AUTH_USER_MODEL, verbose_name='Добавил')),
                ('currency', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='deal_additional_services', to='education.currency', verbose_name='Валюта')),
                ('deal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='additional_services', to='finance.deal', verbose_name='Договор')),
            ],
            options={
                'verbose_name': 'Дополнительная услуга договора',
                'verbose_name_plural': 'Дополнительные услуги договоров',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='dealadditionalservice',
            index=models.Index(fields=['deal', 'created_at'], name='finance_dea_deal_id_4382f4_idx'),
        ),
        migrations.RunSQL(
            sql="""
            INSERT INTO finance_financesettings (id, usd_to_tmt, updated_at, updated_by_id)
            VALUES (1, 19.600000, CURRENT_TIMESTAMP, NULL)
            ON CONFLICT (id) DO NOTHING;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(backfill_finance_data, noop_reverse),
        migrations.AlterField(
            model_name='deal',
            name='deal_type',
            field=models.CharField(choices=[('university', 'Поступление в вуз'), ('service', 'Услуга'), ('other', 'Другое')], db_index=True, default='service', max_length=32, verbose_name='Deal type'),
        ),
        migrations.AlterField(
            model_name='deal',
            name='payment_status',
            field=models.CharField(choices=[('new', 'Не оплачен'), ('paid_partial', 'Оплачен частично'), ('paid_full', 'Оплачен полностью'), ('refunded', 'Возврат'), ('cancelled', 'Отменён')], db_index=True, default='new', max_length=32, verbose_name='Payment status'),
        ),
        migrations.AlterField(
            model_name='payment',
            name='method',
            field=models.CharField(choices=[('cash', 'Наличные'), ('card', 'Карта'), ('bank', 'Банк'), ('transfer', 'Перевод'), ('online', 'Онлайн'), ('other', 'Другое')], db_index=True, default='cash', max_length=32, verbose_name='Method'),
        ),
    ]
