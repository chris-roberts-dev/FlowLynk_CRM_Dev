from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.organizations"
    label = "platform_organizations"
    verbose_name = "Organizations"
