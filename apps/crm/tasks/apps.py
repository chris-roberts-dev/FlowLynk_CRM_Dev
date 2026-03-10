from django.apps import AppConfig


class TasksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm.tasks"
    label = "crm_tasks"
    verbose_name = "Tasks"
