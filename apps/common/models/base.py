"""
apps.common.models.base — Abstract base models for FlowLynk.

All tenant-scoped models should inherit from TenantModel.
All models that need created_at / updated_at should inherit from TimestampedModel.
"""
from django.db import models

from apps.common.tenancy.managers import TenantManager, UnscopedTenantManager


class TimestampedModel(models.Model):
    """Abstract base providing created_at / updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AuditFieldsMixin(models.Model):
    """
    Mixin that adds created_by / updated_by foreign keys.

    These point to Membership (not User) because every tenant action
    is performed in the context of a membership.

    The FK target is a string to avoid circular imports.
    """

    created_by = models.ForeignKey(
        "platform_accounts.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Membership that created this record.",
    )
    updated_by = models.ForeignKey(
        "platform_accounts.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Membership that last updated this record.",
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """
    Abstract mixin for soft-deletable models.

    Use with a custom manager that filters out deleted rows by default.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "platform_accounts.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True


class TenantModel(TimestampedModel, AuditFieldsMixin):
    """
    Abstract base for every tenant-scoped model.

    Adds:
    - organization FK (direct tenant scoping — Pattern A)
    - Timestamps (created_at, updated_at)
    - Audit fields (created_by, updated_by)
    - TenantManager as default manager (auto-filters by current org context)
    - UnscopedTenantManager as escape hatch (Model.unscoped_objects.all())
    """

    organization = models.ForeignKey(
        "platform_organizations.Organization",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        help_text="Owning organization (tenant).",
    )

    # Default manager: auto-scopes to current organization context.
    # Falls back to unfiltered if no context is set (management commands, migrations).
    objects = TenantManager()

    # Escape hatch: never auto-filters. Use for platform admin, data migrations,
    # cross-tenant reporting.
    unscoped_objects = UnscopedTenantManager()

    class Meta:
        abstract = True
        # Composite index on (organization, created_at) added by
        # concrete subclasses via Meta.indexes.
