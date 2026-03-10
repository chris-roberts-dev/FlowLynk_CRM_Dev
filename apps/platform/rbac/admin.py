"""
apps.platform.rbac.admin — RBAC admin configuration.

- Capability: read-only for membership users, full CRUD for superusers
- Role: org-scoped with inline capability grants and scope rules
- MembershipRole: manageable by membership users
"""

from django.contrib import admin

from apps.common.admin.base import _has_membership
from apps.common.admin.sites import flowlynk_admin_site
from apps.platform.rbac.models import (
    Capability,
    MembershipRole,
    Role,
    RoleCapability,
    ScopeRule,
)


# ──────────────────────────────────────────────
# Capability (global — read-only for tenant users)
# ──────────────────────────────────────────────
@admin.register(Capability, site=flowlynk_admin_site)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ("code", "description", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "description")
    readonly_fields = ("created_at", "updated_at")

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return _has_membership(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# ──────────────────────────────────────────────
# Role (org-scoped) with inlines
# ──────────────────────────────────────────────
class RoleCapabilityInline(admin.TabularInline):
    model = RoleCapability
    extra = 1
    autocomplete_fields = ("capability",)


class ScopeRuleInline(admin.TabularInline):
    model = ScopeRule
    extra = 0


@admin.register(Role, site=flowlynk_admin_site)
class RoleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "organization",
        "is_system",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "is_system", "organization")
    search_fields = ("name", "code")
    readonly_fields = ("created_at", "updated_at")
    inlines = [RoleCapabilityInline, ScopeRuleInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        org = getattr(request, "organization", None)
        if org is not None:
            qs = qs.filter(organization=org)
        return qs

    def get_exclude(self, request, obj=None):
        org = getattr(request, "organization", None)
        if org is not None:
            return ["organization"]
        return []

    def save_model(self, request, obj, form, change):
        org = getattr(request, "organization", None)
        if not change and org is not None:
            obj.organization = org
        super().save_model(request, obj, form, change)

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


# ──────────────────────────────────────────────
# MembershipRole
# ──────────────────────────────────────────────
@admin.register(MembershipRole, site=flowlynk_admin_site)
class MembershipRoleAdmin(admin.ModelAdmin):
    list_display = ("membership", "role", "created_at")
    list_filter = ("role__organization",)
    raw_id_fields = ("membership", "role")
    readonly_fields = ("created_at", "updated_at")

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
