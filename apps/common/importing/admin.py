"""
apps.common.importing.admin — ImportRun admin (read-only history).
"""

from django.contrib import admin

from apps.common.admin.base import _has_membership
from apps.common.admin.sites import flowlynk_admin_site
from apps.common.importing.models import ImportRun


@admin.register(ImportRun, site=flowlynk_admin_site)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = (
        "import_type",
        "file_name",
        "status",
        "is_dry_run",
        "row_count",
        "created_count",
        "updated_count",
        "error_count",
        "started_at",
    )
    list_filter = ("import_type", "status", "is_dry_run", "organization")
    search_fields = ("file_name",)
    readonly_fields = (
        "organization",
        "actor_membership",
        "import_type",
        "file_name",
        "status",
        "is_dry_run",
        "row_count",
        "created_count",
        "updated_count",
        "unchanged_count",
        "error_count",
        "errors_json",
        "started_at",
        "completed_at",
        "created_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        org = getattr(request, "organization", None)
        if org is not None and not request.user.is_superuser:
            qs = qs.filter(organization=org)
        return qs

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return _has_membership(request)
