"""
apps.common.admin.base — Reusable admin base classes for FlowLynk.

TenantScopedAdmin:
  - Filters querysets by request.organization (set by TenantMiddleware)
  - Auto-injects organization on save
  - Auto-injects created_by / updated_by from request membership
  - Grants model-level permissions to users with active memberships
    (Phase 1: membership = full access within org. Phase 2+: RBAC capabilities
     will control granular view/add/change/delete permissions.)

Admin is NOT a security boundary — RBAC is enforced in the service layer.
Admin permissions here are a UX convenience, not a security gate.
"""

from django.contrib import admin


def _has_membership(request) -> bool:
    """Check if request has an active membership (set by TenantMiddleware)."""
    membership = getattr(request, "membership", None)
    return membership is not None and membership.is_active


class TenantScopedAdmin(admin.ModelAdmin):
    """
    Base ModelAdmin for any tenant-scoped model.

    Subclasses get automatic:
    - queryset filtering by organization
    - organization + audit field injection on save
    - permission grants for users with active memberships
    """

    # Fields that should be excluded from the form (auto-set)
    # Subclasses can extend this tuple.
    tenant_auto_fields = ("organization", "created_by", "updated_by")

    # ── Queryset scoping ─────────────────────────

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        org = getattr(request, "organization", None)
        if org is not None:
            qs = qs.filter(organization=org)

        # Apply RBAC scope filtering if:
        # 1. Not a superuser (superusers always see everything)
        # 2. The model declares at least one scope_field_*
        # 3. The membership exists
        membership = getattr(request, "membership", None)
        if (
            not request.user.is_superuser
            and membership is not None
            and membership.pk is not None
            and self._model_has_scope_fields()
        ):
            from apps.common.tenancy.scoping import apply_scope

            qs = apply_scope(qs, membership, self.model)

        return qs

    def _model_has_scope_fields(self):
        """Check if the model declares any scope filter paths."""
        return any(
            [
                getattr(self.model, "scope_field_region", None),
                getattr(self.model, "scope_field_market", None),
                getattr(self.model, "scope_field_location", None),
                getattr(self.model, "scope_field_assigned_to", None),
            ]
        )

    # ── Form field exclusion ─────────────────────

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        for field in self.tenant_auto_fields:
            if field not in exclude:
                exclude.append(field)
        return exclude

    # ── Auto-inject on save ──────────────────────

    def save_model(self, request, obj, form, change):
        """Inject organization and audit fields before save."""
        org = getattr(request, "organization", None)
        membership = getattr(request, "membership", None)

        if not change and org is not None:
            obj.organization = org

        if membership is not None:
            if not change:
                obj.created_by = membership
            obj.updated_by = membership

        super().save_model(request, obj, form, change)

    # ── Permission overrides ─────────────────────
    # Phase 1: active membership in the resolved org = full CRUD access
    # to all tenant-scoped models. This is safe because:
    # 1. Admin is not a security boundary (RBAC enforced in service layer)
    # 2. Queryset scoping prevents cross-tenant data access
    # 3. Superusers already have access via is_staff
    # Phase 2+: these can be tightened to check RBAC capabilities.

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return _has_membership(request)
