from django.apps import AppConfig


class SheetsSyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sheets_sync'
    verbose_name = 'Интеграция Google Sheets'
