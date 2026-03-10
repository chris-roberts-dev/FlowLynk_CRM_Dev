"""
apps.platform.organizations.models — Organization (tenant root).

This is the top-level entity for row-based multi-tenancy.
Every tenant-scoped model ultimately references an Organization.
"""
from django.db import models

from apps.common.models.base import TimestampedModel


class OrganizationStatus(models.TextChoices):
    TRIAL = "TRIAL", "Trial"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"


class Organization(TimestampedModel):
    """
    Represents a tenant (franchise, company, or business unit).

    slug is used for subdomain-based tenant resolution:
        {slug}.lvh.me  (dev)
        {slug}.flowlynk.com  (prod)
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=63,
        unique=True,
        help_text="URL-safe identifier. Used as subdomain for tenant resolution.",
    )
    status = models.CharField(
        max_length=20,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.TRIAL,
        db_index=True,
    )
    settings = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tenant-level configuration (timezone, defaults, feature flags, etc.).",
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"], name="idx_org_slug"),
            models.Index(fields=["status"], name="idx_org_status"),
        ]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    @property
    def is_active(self):
        return self.status == OrganizationStatus.ACTIVE

    @property
    def is_suspended(self):
        return self.status == OrganizationStatus.SUSPENDED
