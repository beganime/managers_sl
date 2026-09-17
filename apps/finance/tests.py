from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.crm.models import Client
from apps.education.models import Currency
from apps.finance.models import (
    Cashbox,
    Deal,
    DealAdditionalService,
    EmployeeBalance,
    Expense,
    ExpenseCategory,
    FinanceSettings,
    Income,
    Transaction,
    Payment,
)
from apps.organizations.models import Company, Office


class FinanceContractTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='finance-manager@example.com',
            password='test-password',
            first_name='Анна',
        )
        self.company = Company.objects.create(name='Students Life', country='Туркменистан')
        self.office = Office.objects.create(
            company=self.company,
            name='Ашгабад',
            country='Туркменистан',
            city='Ашгабад',
        )
        self.usd = Currency.objects.create(
            code='USD', name='US Dollar', symbol='$', rate_to_usd=Decimal('1.000000')
        )
        self.tmt = Currency.objects.create(
            code='TMT', name='Туркменский манат', symbol='TMT', rate_to_usd=Decimal('0.051020')
        )
        self.usd_cashbox = Cashbox.objects.create(
            company=self.company,
            office=self.office,
            name='USD',
            currency=self.usd,
        )
        self.tmt_cashbox = Cashbox.objects.create(
            company=self.company,
            office=self.office,
            name='TMT',
            currency=self.tmt,
        )
        self.client_record = Client.objects.create(
            company=self.company,
            office=self.office,
            manager=self.user,
            full_name='Иванов Иван Иванович',
            phone='+99361111111',
            sl_id='SL-2027-001',
        )
        settings_row = FinanceSettings.load()
        settings_row.usd_to_tmt = Decimal('19.600000')
        settings_row.save(update_fields=['usd_to_tmt', 'updated_at'])
        self.contract = Deal.objects.create(
            company=self.company,
            office=self.office,
            client=self.client_record,
            manager=self.user,
            title='Поступление',
            currency=self.usd,
            price_client=Decimal('2000.00'),
        )

    def test_contract_gets_number_and_additional_service_changes_total(self):
        self.assertRegex(self.contract.contract_number, r'^SL-DOG-\d{4}-\d{5}$')

        DealAdditionalService.objects.create(
            deal=self.contract,
            title='Аппликационный сбор',
            amount=Decimal('100.00'),
            currency=self.usd,
            created_by=self.user,
        )

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.total_to_pay_usd, Decimal('2100.00'))

    def test_partial_payment_updates_office_employee_and_progress_once(self):
        payment = Payment.objects.create(
            company=self.company,
            office=self.office,
            deal=self.contract,
            client=self.client_record,
            manager=self.user,
            cashbox=self.usd_cashbox,
            amount=Decimal('300.00'),
            currency=self.usd,
        )

        payment.confirm(user=self.user)
        payment.confirm(user=self.user)

        self.usd_cashbox.refresh_from_db()
        self.contract.refresh_from_db()
        balance = EmployeeBalance.objects.get(employee=self.user)
        self.assertEqual(self.usd_cashbox.balance, Decimal('300.00'))
        self.assertEqual(balance.balance_tmt, Decimal('5880.00'))
        self.assertEqual(self.contract.paid_amount_usd, Decimal('300.00'))
        self.assertEqual(self.contract.payment_progress, 15)
        self.assertEqual(self.contract.payment_status, Deal.PAYMENT_STATUS_PARTIAL)

    def test_expense_reduces_office_and_employee_balance(self):
        EmployeeBalance.objects.create(
            employee=self.user,
            office=self.office,
            balance_tmt=Decimal('500.00'),
        )
        category = ExpenseCategory.objects.create(
            company=self.company,
            name='Офисные расходы',
            code='office-costs',
        )
        expense = Expense.objects.create(
            company=self.company,
            office=self.office,
            category=category,
            employee=self.user,
            cashbox=self.tmt_cashbox,
            title='Канцелярия',
            amount=Decimal('100.00'),
            currency=self.tmt,
        )

        expense.confirm(user=self.user)
        expense.confirm(user=self.user)

        self.tmt_cashbox.refresh_from_db()
        balance = EmployeeBalance.objects.get(employee=self.user)
        self.assertEqual(self.tmt_cashbox.balance, Decimal('-100.00'))
        self.assertEqual(balance.balance_tmt, Decimal('400.00'))


class FinanceEntryApiTests(FinanceContractTests):
    def setUp(self):
        super().setUp()
        from apps.employees.models import EmployeeProfile, EmployeeRole
        from rest_framework.test import APIClient
        role = EmployeeRole.objects.create(code='manager', name='Менеджер', role_type='manager')
        EmployeeProfile.objects.create(user=self.user, company=self.company, office=self.office, role=role)
        self.admin = get_user_model().objects.create_superuser(email='finance-admin@example.com', password='test-password')
        self.other_office = Office.objects.create(company=self.company, name='Мары', country='Туркменистан', city='Мары')
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_mobile_expense_without_category_uses_office_and_tmt(self):
        response = self.api.post('/api/v1/finance/expenses/', {'title': 'Канцелярия', 'amount': '196', 'date': '2026-09-03'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        expense = Expense.objects.get(pk=response.data['id'])
        self.assertEqual(expense.category.code, 'other')
        self.assertEqual(expense.employee, self.user)
        self.assertTrue(expense.is_confirmed)
        self.assertEqual(expense.amount_usd, Decimal('10'))
        self.assertEqual(expense.amount_tmt, Decimal('196'))
        self.assertEqual(expense.office, self.office)

    def test_employee_cannot_top_up_or_use_another_office(self):
        payload = {'title': 'Проверка', 'amount': '20', 'office': self.other_office.pk}
        self.assertEqual(self.api.post('/api/v1/finance/expenses/', payload).status_code, 403)
        self.assertEqual(self.api.post('/api/v1/finance/incomes/', payload).status_code, 403)
        self.assertFalse(Income.objects.exists())
        self.assertFalse(Expense.objects.exists())

    def test_admin_top_up_usd_no_employee_commission(self):
        self.api.force_authenticate(self.admin)
        response = self.api.post('/api/v1/finance/incomes/', {'title': 'На работу офиса', 'amount': '100', 'office': self.other_office.pk, 'entry_currency': 'USD'})
        self.assertEqual(response.status_code, 201, response.data)
        income = Income.objects.get(pk=response.data['id'])
        self.assertEqual(income.amount_tmt, Decimal('1960'))
        self.assertIsNone(income.employee)
        self.assertEqual(income.confirmed_by, self.admin)
        self.assertEqual(income.cashbox.balance, Decimal('100'))
        self.assertEqual(self.api.patch(f'/api/v1/finance/incomes/{income.pk}/', {'amount': '999'}).status_code, 405)
        self.assertEqual(self.api.delete(f'/api/v1/finance/incomes/{income.pk}/').status_code, 405)

    def test_summary_does_not_include_other_office(self):
        Income.objects.create(company=self.company, office=self.other_office, cashbox=self.usd_cashbox, title='Чужой офис', amount=100, currency=self.usd).confirm(self.admin)
        response = self.api.get('/api/v1/finance/transactions/summary/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['month_income_tmt'], Decimal('0'))
        self.assertEqual(len(response.data['offices']), 1)
        self.assertFalse(response.data['can_top_up'])

    def test_confirmation_uses_saved_rate_and_stale_instances_only_post_once(self):
        income = Income.objects.create(company=self.company, office=self.office, cashbox=self.usd_cashbox, title='Курс', amount=100, currency=self.usd)
        stale = Income.objects.get(pk=income.pk)
        FinanceSettings.objects.update(usd_to_tmt=Decimal('25'))
        income.confirm(self.admin)
        stale.confirm(self.admin)
        self.usd_cashbox.refresh_from_db()
        self.assertEqual(self.usd_cashbox.balance, Decimal('100'))
        self.assertEqual(stale.amount_tmt, Decimal('1960'))
        self.assertEqual(Transaction.objects.filter(related_income=income).count(), 1)

    def test_server_validates_amount_and_comment(self):
        for amount in ('0', '-1', 'NaN', '1.123'):
            response = self.api.post('/api/v1/finance/expenses/', {'title': 'Проверка', 'amount': amount})
            self.assertEqual(response.status_code, 400, response.data)
        response = self.api.post('/api/v1/finance/expenses/', {'title': 'Проверка', 'amount': '1', 'comment': 'x' * 1001})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Expense.objects.exists())

    def test_portal_expense_without_category(self):
        self.client.force_login(self.user)
        response = self.client.post('/portal/finance/expense/', {'title': 'Бумага', 'amount': '50', 'date': '2026-09-03', 'office': self.office.pk, 'currency': self.tmt.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Expense.objects.get().category.code, 'other')

    def test_user_without_office_sees_no_balances(self):
        self.user.employee_profile.office = None
        self.user.employee_profile.save(update_fields=['office'])
        response = self.api.get('/api/v1/finance/transactions/summary/')
        self.assertEqual(response.data['offices'], [])
        self.assertEqual(response.data['cashbox_balance_tmt'], Decimal('0'))
        self.assertEqual(self.api.post('/api/v1/finance/expenses/', {'title': 'Проверка', 'amount': '1'}).status_code, 400)
