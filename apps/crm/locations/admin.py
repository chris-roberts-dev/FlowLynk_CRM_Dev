"""
apps.crm.locations.admin — Location hierarchy admin.

Region, Market, Location with hierarchy display, inline children, and CSV import.
The import button is on the Region list — it imports the full hierarchy
(Regions, Markets, Locations) from a single CSV.
"""

from django.contrib import admin

from apps.common.admin import TenantScopedAdmin, flowlynk_admin_site
from apps.common.admin.import_mixin import ImportCSVMixin
from apps.crm.locations.models import Location, Market, Region


# ──────────────────────────────────────────────
# Inlines
# ──────────────────────────────────────────────
class MarketInline(admin.TabularInline):
    model = Market
    extra = 0
    fields = ("code", "name", "is_active")
    show_change_link = True


class LocationInline(admin.TabularInline):
    model = Location
    extra = 0
    fields = ("code", "name", "city", "state", "is_active")
    show_change_link = True


# ──────────────────────────────────────────────
# Region (with hierarchy CSV import)
# ──────────────────────────────────────────────
@admin.register(Region, site=flowlynk_admin_site)
class RegionAdmin(ImportCSVMixin, TenantScopedAdmin):
    # Import configuration — imports full hierarchy (Region → Market → Location)
    import_url_name = "location-import"
    import_button_label = "Import Locations CSV"
    import_page_title = "Import Location Hierarchy"
    change_list_template = "admin/import_changelist.html"

    def get_importer(self, organization, membership=None):
        from apps.crm.locations.services import LocationImporter

        return LocationImporter(organization=organization, membership=membership)

    # Standard admin config
    list_display = ("name", "code", "is_active", "market_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    readonly_fields = ("created_at", "updated_at")
    inlines = [MarketInline]

    @admin.display(description="Markets")
    def market_count(self, obj):
        return obj.markets.count()


# ──────────────────────────────────────────────
# Market
# ──────────────────────────────────────────────
@admin.register(Market, site=flowlynk_admin_site)
class MarketAdmin(TenantScopedAdmin):
    list_display = (
        "name",
        "code",
        "region",
        "is_active",
        "location_count",
        "created_at",
    )
    list_filter = ("is_active", "region")
    search_fields = ("name", "code")
    readonly_fields = ("created_at", "updated_at")
    inlines = [LocationInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("region")

    @admin.display(description="Locations")
    def location_count(self, obj):
        return obj.locations.count()


# ──────────────────────────────────────────────
# Location
# ──────────────────────────────────────────────
@admin.register(Location, site=flowlynk_admin_site)
class LocationAdmin(TenantScopedAdmin):
    list_display = (
        "name",
        "code",
        "market",
        "city",
        "state",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "market__region", "state")
    search_fields = ("name", "code", "city", "postal_code")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("code", "name", "market", "is_active")}),
        ("Address", {"fields": ("street", "city", "state", "postal_code", "country")}),
        (
            "Operations",
            {"fields": ("timezone", "operating_hours", "capacity", "service_area")},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("market", "market__region")
