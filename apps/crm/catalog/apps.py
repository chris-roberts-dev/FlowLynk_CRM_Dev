from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm.catalog"
    label = "crm_catalog"
    verbose_name = "Catalog"
