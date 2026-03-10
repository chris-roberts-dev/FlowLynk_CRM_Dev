from django.apps import AppConfig


class AssignmentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scheduling.assignments"
    label = "scheduling_assignments"
    verbose_name = "Assignments"
