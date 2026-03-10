from django.apps import AppConfig


class RbacConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.platform.rbac"
    label = "platform_rbac"
    verbose_name = "RBAC"
