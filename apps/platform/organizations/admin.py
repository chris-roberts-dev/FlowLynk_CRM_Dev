"""
apps.platform.organizations.admin — Organization admin configuration.
"""
from django.contrib import admin

from apps.common.admin.sites import flowlynk_admin_site
from apps.platform.organizations.models import Organization


@admin.register(Organization, site=flowlynk_admin_site)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
