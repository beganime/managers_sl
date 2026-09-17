"""Shared student visibility policy for the portal and authenticated CRM API."""
from django.db.models import Q
from apps.core.permissions import get_employee_profile, is_erp_admin


def visible_clients(queryset, user):
    if not user or not user.is_authenticated:
        return queryset.none()
    if is_erp_admin(user):
        return queryset
    scope = Q(manager=user)
    employee = get_employee_profile(user)
    if employee and employee.company_id:
        scope |= Q(is_public=True, company_id=employee.company_id)
    return queryset.filter(scope).distinct()


def visible_onboarding(queryset, user):
    from .models import Client
    if is_erp_admin(user):
        return queryset
    return queryset.filter(Q(client__isnull=True) | Q(client_id__in=visible_clients(Client.objects.all(), user).values('pk')))
