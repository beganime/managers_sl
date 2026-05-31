from django.apps import AppConfig


class CustomFieldsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.customfields'
    verbose_name = 'Настройки полей'
