from django.apps import AppConfig


class ClientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm.clients"
    label = "crm_clients"
    verbose_name = "Clients"
