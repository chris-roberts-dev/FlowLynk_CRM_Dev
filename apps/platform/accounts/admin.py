"""
apps.platform.accounts.admin — User and Membership admin configuration.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.common.admin.sites import flowlynk_admin_site
from apps.platform.accounts.models import Membership, User


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    readonly_fields = ("created_at", "last_login_at")
    raw_id_fields = ("organization",)


@admin.register(User, site=flowlynk_admin_site)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "first_name", "last_name", "status", "is_staff", "created_at")
    list_filter = ("status", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login")
    inlines = [MembershipInline]

    # Override fieldsets for email-based user (no username)
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


@admin.register(Membership, site=flowlynk_admin_site)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "status", "created_at", "last_login_at")
    list_filter = ("status", "organization")
    search_fields = ("user__email", "organization__name")
    raw_id_fields = ("user", "organization")
    readonly_fields = ("created_at", "updated_at", "last_login_at")
