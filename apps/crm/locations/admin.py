"""
apps.crm.locations.admin — Location admin configuration.

Uses TenantScopedAdmin to auto-filter by organization.
Full hierarchy admin (Region/Market inlines) built in EPIC 5.
"""
from apps.common.admin import TenantScopedAdmin, flowlynk_admin_site
from apps.crm.locations.models import Location


@flowlynk_admin_site.register(Location)
class LocationAdmin(TenantScopedAdmin):
    list_display = ("name", "code", "organization", "created_at")
    search_fields = ("name", "code")
    readonly_fields = ("created_at", "updated_at")
