from types import MethodType


LEGACY_ADMIN_APP_LABELS = {
    'analytics',
    'catalog',
    'clients',
    'documents',
    'leads',
    'services',
    'tasks',
    'timetracking',
}


def apply_admin_cleanup():
    """Hide legacy admin sections from regular staff while keeping models registered."""
    try:
        from django.contrib import admin
    except Exception:
        return

    for model, model_admin in list(admin.site._registry.items()):
        if model._meta.app_label not in LEGACY_ADMIN_APP_LABELS:
            continue
        if getattr(model_admin, '_managers_sl_legacy_hidden', False):
            continue

        original_get_model_perms = model_admin.get_model_perms

        def get_model_perms(self, request, _original=original_get_model_perms):
            if request.user.is_superuser:
                return _original(request)
            return {}

        model_admin.get_model_perms = MethodType(get_model_perms, model_admin)
        model_admin._managers_sl_legacy_hidden = True
