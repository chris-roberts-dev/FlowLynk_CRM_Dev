from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm.pricing"
    label = "crm_pricing"
    verbose_name = "Pricing"
