"""
apps.crm.locations.models — Location hierarchy: Region → Market → Location.

Region: top-level geographic grouping (e.g. "Southeast", "Pacific Northwest")
Market: sub-region grouping (e.g. "Atlanta Metro", "Portland")
Location: a physical operating location with address and capacity details

All three levels are org-scoped with code uniqueness per org.
"""

from django.db import models

from apps.common.models.base import TenantModel


class Region(TenantModel):
    """
    Top-level geographic grouping within an organization.

    Examples: "Southeast", "Pacific Northwest", "Midwest".
    """

    # Scope: a region-scoped user sees only their assigned region
    scope_field_region = "pk"

    code = models.CharField(
        max_length=50,
        help_text="Unique code within the org, e.g. 'SE', 'PNW'.",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uq_region_org_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="idx_region_org_created",
            ),
        ]
        ordering = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Market(TenantModel):
    """
    Sub-region grouping within a Region.

    Examples: "Atlanta Metro", "Portland", "Orlando".
    """

    # Scope: region-scoped users see markets in their region;
    # market-scoped users see only their assigned market
    scope_field_region = "region"
    scope_field_market = "pk"

    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="markets",
    )
    code = models.CharField(
        max_length=50,
        help_text="Unique code within the org, e.g. 'ATL', 'PDX'.",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uq_market_org_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="idx_market_org_created",
            ),
        ]
        ordering = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Location(TenantModel):
    """
    A physical operating location within a Market.

    Stores address, timezone, service area, operating hours,
    and capacity details needed for scheduling and routing.
    """

    # Scope: full hierarchy filtering
    scope_field_region = "market__region"
    scope_field_market = "market"
    scope_field_location = "pk"

    market = models.ForeignKey(
        Market,
        on_delete=models.CASCADE,
        related_name="locations",
        null=True,
        blank=True,
        help_text="Parent market. Null allowed during migration from stub.",
    )
    code = models.CharField(
        max_length=50,
        help_text="Unique code within the org, e.g. 'ATL-001'.",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True, db_index=True)

    # Address
    street = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="US")

    # Timezone (e.g. "America/New_York")
    timezone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="IANA timezone, e.g. 'America/New_York'. Falls back to org default.",
    )

    # Service area (future: zip list, radius, polygon)
    service_area = models.JSONField(
        default=dict,
        blank=True,
        help_text="Service area config: {zips: [...], radius_miles: N, polygon: [...]}",
    )

    # Operating hours + capacity
    operating_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text='Operating hours: {"mon": {"start": "07:00", "end": "18:00"}, ...}',
    )
    capacity = models.JSONField(
        default=dict,
        blank=True,
        help_text="Capacity constraints: {max_daily_visits: N, max_teams: N, ...}",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uq_location_org_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="idx_location_org_created",
            ),
            models.Index(
                fields=["organization", "is_active"],
                name="idx_location_org_active",
            ),
        ]
        ordering = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def full_hierarchy(self):
        """Return 'Region > Market > Location' display string."""
        parts = []
        if self.market:
            if self.market.region:
                parts.append(self.market.region.name)
            parts.append(self.market.name)
        parts.append(self.name)
        return " > ".join(parts)
