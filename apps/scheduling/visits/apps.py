from django.apps import AppConfig


class VisitsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduling.visits"
    label = "scheduling_visits"
    verbose_name = "Visits"
