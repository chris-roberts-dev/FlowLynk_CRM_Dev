from django.apps import AppConfig


class ImportingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common.importing"
    label = "common_importing"
    verbose_name = "Importing"
