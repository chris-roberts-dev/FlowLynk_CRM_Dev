"""
apps.common.tenancy.managers — Tenant-aware querysets and managers.

Full implementation in EPIC 1. Provides the interface now so that
model definitions can reference TenantManager.
"""
from django.db import models


class TenantQuerySet(models.QuerySet):
    """QuerySet that can filter by organization."""

    def for_organization(self, organization):
        """Filter to records owned by the given organization."""
        return self.filter(organization=organization)


class TenantManager(models.Manager):
    """
    Default manager for tenant-scoped models.

    In EPIC 1 this will auto-apply tenant filtering from thread-local
    or request context. For now it provides explicit for_organization().
    """

    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_organization(self, organization):
        return self.get_queryset().for_organization(organization)
