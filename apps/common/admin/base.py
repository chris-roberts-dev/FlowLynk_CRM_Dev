"""
apps.common.admin.base — Reusable admin base classes for FlowLynk.

TenantScopedAdmin:
  - Filters querysets by request.organization (set by TenantMiddleware in EPIC 1)
  - Auto-injects organization on save
  - Auto-injects created_by / updated_by from request membership

Until EPIC 1 wires the middleware, these gracefully fall back to
unfiltered querysets for superusers.
"""
from django.contrib import admin


class TenantScopedAdmin(admin.ModelAdmin):
    """
    Base ModelAdmin for any tenant-scoped model.

    Subclasses get automatic:
    - queryset filtering by organization
    - organization + audit field injection on save
    """

    # Fields that should be excluded from the form (auto-set)
    # Subclasses can extend this tuple.
    tenant_auto_fields = ("organization", "created_by", "updated_by")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        org = getattr(request, "organization", None)
        if org is not None:
            qs = qs.filter(organization=org)
        return qs

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        for field in self.tenant_auto_fields:
            if field not in exclude:
                exclude.append(field)
        return exclude

    def save_model(self, request, obj, form, change):
        """Inject organization and audit fields before save."""
        org = getattr(request, "organization", None)
        membership = getattr(request, "membership", None)

        if not change and org is not None:
            # New object — set organization
            obj.organization = org

        if membership is not None:
            if not change:
                obj.created_by = membership
            obj.updated_by = membership

        super().save_model(request, obj, form, change)
