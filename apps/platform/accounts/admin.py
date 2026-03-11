"""
apps.platform.accounts.admin — User, Membership, and TenantMember admin.

Platform admins (superusers): see User and Membership (global view).
Tenant admins (members): see TenantMember (org-scoped member management).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import IntegrityError

from apps.common.admin.base import _has_membership
from apps.common.admin.sites import flowlynk_admin_site
from apps.platform.accounts.forms import TenantMemberAddForm, TenantMemberChangeForm
from apps.platform.accounts.models import Membership, TenantMember, User
from apps.platform.rbac.models import MembershipRole


# ──────────────────────────────────────────────
# Inlines
# ──────────────────────────────────────────────
class MembershipInline(admin.TabularInline):
    """Inline on User admin (superuser view)."""

    model = Membership
    extra = 0
    readonly_fields = ("created_at", "last_login_at")
    raw_id_fields = ("organization",)


class MembershipRoleInline(admin.TabularInline):
    """Inline on Membership/TenantMember admin to assign roles."""

    model = MembershipRole
    extra = 1
    readonly_fields = ("created_at",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit role choices to the current org's roles."""
        if db_field.name == "role":
            org = getattr(request, "organization", None)
            if org is not None:
                from apps.platform.rbac.models import Role

                kwargs["queryset"] = Role.objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ──────────────────────────────────────────────
# User admin (superuser only — global view)
# ──────────────────────────────────────────────
@admin.register(User, site=flowlynk_admin_site)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "status",
        "is_staff",
        "created_at",
    )
    list_filter = ("status", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login")
    inlines = [MembershipInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Status", {"fields": ("status", "is_active")}),
        (
            "Permissions",
            {
                "fields": ("is_staff", "is_superuser", "groups", "user_permissions"),
            },
        ),
        ("Timestamps", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


# ──────────────────────────────────────────────
# Membership admin (superuser only — global view)
# ──────────────────────────────────────────────
@admin.register(Membership, site=flowlynk_admin_site)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "status", "created_at", "last_login_at")
    list_filter = ("status", "organization")
    search_fields = ("user__email", "organization__name")
    raw_id_fields = ("user", "organization")
    readonly_fields = ("created_at", "updated_at", "last_login_at")
    inlines = [MembershipRoleInline]


# ──────────────────────────────────────────────
# TenantMember admin (tenant-facing member management)
# ──────────────────────────────────────────────
@admin.register(TenantMember, site=flowlynk_admin_site)
class TenantMemberAdmin(admin.ModelAdmin):
    """
    Tenant-facing admin for managing organization members.

    Appears as "Members" under the CRM group. Allows tenant admins to:
    - See all members in their organization
    - Add new members (creates User if needed + Membership)
    - Edit membership status
    - Assign roles via inline

    The add form collects email + name + password and handles
    User get_or_create logic transparently.
    """

    list_display = (
        "get_email",
        "get_first_name",
        "get_last_name",
        "status",
        "get_assignment",
        "last_login_at",
        "created_at",
    )
    list_filter = ("status", "assigned_region", "assigned_market")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at", "last_login_at")
    inlines = [MembershipRoleInline]

    # ── Display helpers ──────────────────────

    @admin.display(description="Email", ordering="user__email")
    def get_email(self, obj):
        return obj.user.email

    @admin.display(description="First Name", ordering="user__first_name")
    def get_first_name(self, obj):
        return obj.user.first_name

    @admin.display(description="Last Name", ordering="user__last_name")
    def get_last_name(self, obj):
        return obj.user.last_name

    @admin.display(description="Assignment")
    def get_assignment(self, obj):
        """Show the most specific geographic assignment."""
        if obj.default_location:
            return str(obj.default_location)
        if obj.assigned_market:
            return str(obj.assigned_market)
        if obj.assigned_region:
            return str(obj.assigned_region)
        return "—"

    # ── Queryset: org-scoped ─────────────────

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related(
                "user",
                "organization",
                "assigned_region",
                "assigned_market",
                "default_location",
            )
        )
        org = getattr(request, "organization", None)
        if org is not None:
            qs = qs.filter(organization=org)
        return qs

    # ── Form handling ────────────────────────

    def get_form(self, request, obj=None, **kwargs):
        """Use custom add form for new members, change form for existing."""
        if obj is None:
            # Adding a new member
            return TenantMemberAddForm
        else:
            # Editing existing member
            return TenantMemberChangeForm

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [
                (
                    "User Account",
                    {"fields": ("email", "first_name", "last_name", "password")},
                ),
                ("Membership", {"fields": ("status",)}),
            ]
        else:
            return [
                ("User Account", {"fields": ("email", "first_name", "last_name")}),
                ("Membership", {"fields": ("status",)}),
                (
                    "Geographic Assignment",
                    {
                        "fields": (
                            "assigned_region",
                            "assigned_market",
                            "default_location",
                        ),
                        "description": "Assign this member to a region, market, and/or location. These control the member's operating scope.",
                    },
                ),
                (
                    "Timestamps",
                    {"fields": ("last_login_at", "created_at", "updated_at")},
                ),
            ]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("created_at", "updated_at", "last_login_at")

    def save_form(self, request, form, change):
        """
        Override to handle user creation during add.

        Django calls this before save_model. For new members, we need
        to populate user + organization on the instance before Django
        tries to access them (e.g. in __str__ or logging).
        """
        if change:
            return super().save_form(request, form, change)

        # Add flow: build the instance ourselves
        org = getattr(request, "organization", None)
        user = form.get_or_create_user()
        instance = form.save(commit=False)
        instance.user = user
        instance.organization = org
        return instance

    def save_model(self, request, obj, form, change):
        """
        Handle add vs change:
        - Add: user + org already set by save_form, just save
        - Change: standard save
        """
        if not change:
            try:
                obj.save()
            except IntegrityError:
                from django.contrib import messages

                messages.error(
                    request,
                    f"{obj.user.email} is already a member of this organization.",
                )
                return
        else:
            super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """Save inlines (MembershipRole) after the membership is saved."""
        if change:
            super().save_related(request, form, formsets, change)
        else:
            # For new members, we need to handle formsets manually since
            # save_model already created the object
            for formset in formsets:
                formset.save()

    # ── Permission overrides ─────────────────

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
