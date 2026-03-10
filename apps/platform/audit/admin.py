"""
apps.platform.audit.admin — Read-only AuditEvent admin.

Audit events are immutable. The admin provides view-only access
with rich filtering for investigation and compliance.
"""

from django.contrib import admin

from apps.common.admin.base import _has_membership
from apps.common.admin.sites import flowlynk_admin_site
from apps.platform.audit.models import AuditEvent, EventCategory


@admin.register(AuditEvent, site=flowlynk_admin_site)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "category",
        "actor_email",
        "entity_type",
        "entity_id",
        "short_reason",
        "correlation_id_short",
    )
    list_filter = (
        "category",
        "event_type",
        "entity_type",
        "organization",
        ("created_at", admin.DateFieldListFilter),
    )
    search_fields = (
        "event_type",
        "actor_email",
        "entity_type",
        "entity_id",
        "correlation_id",
        "reason",
    )
    readonly_fields = (
        "organization",
        "actor_membership",
        "actor_email",
        "category",
        "event_type",
        "entity_type",
        "entity_id",
        "metadata",
        "reason",
        "correlation_id",
        "ip_address",
        "user_agent",
        "created_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Event",
            {
                "fields": ("event_type", "category", "created_at"),
            },
        ),
        (
            "Actor",
            {
                "fields": ("actor_email", "actor_membership", "organization"),
            },
        ),
        (
            "Entity",
            {
                "fields": ("entity_type", "entity_id"),
            },
        ),
        (
            "Details",
            {
                "fields": ("metadata", "reason"),
            },
        ),
        (
            "Request Context",
            {
                "fields": ("correlation_id", "ip_address", "user_agent"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        org = getattr(request, "organization", None)
        if org is not None and not request.user.is_superuser:
            qs = qs.filter(organization=org)
        return qs

    # ── Display helpers ──────────────────────

    @admin.display(description="Reason")
    def short_reason(self, obj):
        if obj.reason:
            return obj.reason[:60] + "..." if len(obj.reason) > 60 else obj.reason
        return ""

    @admin.display(description="Correlation ID")
    def correlation_id_short(self, obj):
        if obj.correlation_id:
            return obj.correlation_id[:12] + "..."
        return ""

    # ── Read-only enforcement ────────────────

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return _has_membership(request)
