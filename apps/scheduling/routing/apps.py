from django.apps import AppConfig


class RoutingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduling.routing"
    label = "scheduling_routing"
    verbose_name = "Routing"
