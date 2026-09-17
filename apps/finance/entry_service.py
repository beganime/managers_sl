"""Shared, server-owned finance scope for the portal and mobile API."""
from decimal import Decimal

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.permissions import get_employee_profile, is_erp_admin
from apps.education.models import Currency
from apps.organizations.models import Office
from .models import Cashbox, ExpenseCategory, FinanceSettings


def can_manage_finance(user):
    profile = get_employee_profile(user)
    access = getattr(profile, 'access', None)
    return is_erp_admin(user) or bool(access and access.can_manage_finance)


def require_finance_manager(user):
    if not can_manage_finance(user):
        raise PermissionDenied('Пополнять офис и подтверждать оплаты может только администратор.')


def finance_offices(user):
    offices = Office.objects.filter(is_active=True)
    if is_erp_admin(user):
        return offices
    profile = get_employee_profile(user)
    if not profile or not profile.office_id:
        return offices.none()
    return offices.filter(pk=profile.office_id, company_id=profile.company_id)


def finance_scope(queryset, user):
    if is_erp_admin(user):
        return queryset
    return queryset.filter(office__in=finance_offices(user))


def resolve_office(user, office=None):
    if office is None:
        profile = get_employee_profile(user)
        office = profile.office if profile and profile.office_id else None
    if office is None:
        raise ValidationError({'office': 'Выберите офис. Если его нет в списке, попросите администратора назначить вам офис.'})
    if not finance_offices(user).filter(pk=office.pk).exists():
        raise PermissionDenied('Можно добавлять операции только в своём офисе.')
    return office


def entry_currency(code='TMT'):
    if code not in ('TMT', 'USD'):
        raise ValidationError({'entry_currency': 'Выберите TMT или USD.'})
    rate = FinanceSettings.load().usd_to_tmt
    if rate <= 0:
        raise ValidationError('Администратор должен указать курс USD больше нуля.')
    currency, _ = Currency.objects.get_or_create(code=code, defaults={
        'name': 'Туркменский манат' if code == 'TMT' else 'Доллар США',
        'symbol': code if code == 'TMT' else '$',
        'rate_to_usd': Decimal('1') / rate if code == 'TMT' else Decimal('1'),
    })
    return currency


def entry_cashbox(office, currency):
    cashbox, _ = Cashbox.objects.get_or_create(
        company=office.company, office=office, name=currency.code,
        defaults={'currency': currency, 'is_active': True},
    )
    if cashbox.currency_id != currency.pk or not cashbox.is_active:
        raise ValidationError('Касса офиса отключена или имеет неверную валюту. Обратитесь к администратору.')
    return cashbox


def entry_category(company, category=None):
    if category:
        if category.company_id != company.pk or not category.is_active:
            raise ValidationError({'category': 'Выберите действующую категорию своей компании.'})
        return category
    category, _ = ExpenseCategory.objects.get_or_create(
        company=company, code='other', defaults={'name': 'Другое', 'is_active': True},
    )
    return category
