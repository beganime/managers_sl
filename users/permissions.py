from rest_framework.permissions import BasePermission


def is_admin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, 'role', None) == 'admin')
    )


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return is_admin_user(request.user)


class IsAdminOrSelf(BasePermission):
    def has_object_permission(self, request, view, obj):
        return is_admin_user(request.user) or obj == request.user