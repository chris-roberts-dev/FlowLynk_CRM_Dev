"""
apps.crm.locations.models — Location hierarchy (Region → Market → Location).

Full implementation in EPIC 5. Stub Location model needed now because
Membership has an optional FK to Location.
"""
from django.db import models

from apps.common.models.base import TenantModel


class Location(TenantModel):
    """
    A physical operating location within a tenant.

    Stub — full hierarchy (Region → Market → Location) built in EPIC 5.
    """

    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)

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
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"
