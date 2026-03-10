from django.apps import AppConfig


class AgreementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduling.agreements"
    label = "scheduling_agreements"
    verbose_name = "Agreements"
