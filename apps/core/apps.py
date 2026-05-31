from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Настройки'

    def ready(self):
        from .admin_cleanup import apply_admin_cleanup

        apply_admin_cleanup()
