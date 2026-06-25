from django.apps import AppConfig


class ErpDocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.erp_documents'
    verbose_name = 'Документы'

    def ready(self):
        from .runtime_patches import apply_document_generation_patches

        apply_document_generation_patches()
