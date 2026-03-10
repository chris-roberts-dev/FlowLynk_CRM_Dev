from django.apps import AppConfig


class QuotesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm.quotes"
    label = "crm_quotes"
    verbose_name = "Quotes"
