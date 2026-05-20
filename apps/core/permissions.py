def get_employee_profile(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return getattr(user, 'employee_profile', None)


def is_erp_admin(user) -> bool:
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and (
            getattr(user, 'is_superuser', False)
            or getattr(user, 'is_staff', False)
            or getattr(user, 'role', None) == 'admin'
        )
    )


def get_employee_role_type(user) -> str | None:
    employee = get_employee_profile(user)
    if not employee or not employee.role_id:
        return None
    return employee.role.role_type


def filter_by_company_scope(queryset, user, company_field: str = 'company'):
    if is_erp_admin(user):
        return queryset

    employee = get_employee_profile(user)
    if not employee:
        return queryset.none()

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None

    if role_type == 'company_owner' or (access and access.can_see_all_company):
        return queryset.filter(**{company_field: employee.company})

    if role_type == 'office_director' or (access and access.can_see_all_office):
        return queryset.filter(**{company_field: employee.company})

    return queryset.filter(**{company_field: employee.company})


def filter_by_office_scope(queryset, user, company_field: str = 'company', office_field: str = 'office'):
    if is_erp_admin(user):
        return queryset

    employee = get_employee_profile(user)
    if not employee:
        return queryset.none()

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None

    if role_type == 'company_owner' or (access and access.can_see_all_company):
        return queryset.filter(**{company_field: employee.company})

    if role_type == 'office_director' or (access and access.can_see_all_office):
        if employee.office_id:
            return queryset.filter(**{company_field: employee.company, office_field: employee.office})
        return queryset.filter(**{company_field: employee.company})

    if employee.office_id:
        return queryset.filter(**{company_field: employee.company, office_field: employee.office})

    return queryset.filter(**{company_field: employee.company})


def filter_manager_owned(queryset, user, manager_field: str = 'manager'):
    if is_erp_admin(user):
        return queryset

    employee = get_employee_profile(user)
    if not employee:
        return queryset.none()

    access = getattr(employee, 'access', None)
    role_type = employee.role.role_type if employee.role_id else None

    if role_type == 'company_owner' or (access and access.can_see_all_company):
        return queryset.filter(company=employee.company)

    if role_type == 'office_director' or (access and access.can_see_all_office):
        filters = {'company': employee.company}
        if employee.office_id:
            filters['office'] = employee.office
        return queryset.filter(**filters)

    return queryset.filter(**{manager_field: user})
