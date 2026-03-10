from django.apps import AppConfig


class LocationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm.locations"
    label = "crm_locations"
    verbose_name = "Locations"
