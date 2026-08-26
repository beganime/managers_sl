from rest_framework.permissions import BasePermission

from apps.core.permissions import get_employee_profile, is_erp_admin


def can_review_onboarding(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if is_erp_admin(user):
        return True

    employee = get_employee_profile(user)
    if employee:
        return bool(
            employee.is_active
            and employee.work_status != 'fired'
            and employee.role_id
            and employee.role.role_type in {'company_owner', 'office_director', 'manager'}
        )

    # Backward compatibility for installations that have not yet created
    # EmployeeProfile rows for their existing managers.
    return getattr(user, 'role', None) == 'manager'


class CanReviewOnboarding(BasePermission):
    message = 'У сотрудника нет права проверять анкеты.'

    def has_permission(self, request, view):
        return can_review_onboarding(request.user)
