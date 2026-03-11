"""
apps.crm.locations.admin — Location hierarchy admin.

Region, Market, Location with hierarchy display and inline children.
"""

from django.contrib import admin

from apps.common.admin import TenantScopedAdmin, flowlynk_admin_site
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
# Region
# ──────────────────────────────────────────────
@admin.register(Region, site=flowlynk_admin_site)
class RegionAdmin(TenantScopedAdmin):
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
