"""
apps.common.tenancy.managers — Tenant-aware querysets and managers.

TenantManager auto-filters querysets by the current organization from
thread-local context (set by TenantMiddleware). This ensures that tenant
data never leaks across organizations in normal application flows.

Escape hatches:
    Model.objects.unscoped()          — bypasses tenant filter (platform admin, migrations)
    Model.objects.for_organization(o) — explicit org filter (services, tests)
"""
from django.db import models

from apps.common.tenancy.context import get_current_organization


class TenantQuerySet(models.QuerySet):
    """QuerySet with tenant-aware helpers."""

    def for_organization(self, organization):
        """Explicitly filter to records owned by the given organization."""
        return self.filter(organization=organization)


class TenantManager(models.Manager):
    """
    Default manager for tenant-scoped models.

    Behavior:
    - If a tenant context is active (middleware set it), all querysets
      are automatically filtered by organization_id.
    - If no context is active (management commands, migrations, tests
      without middleware), querysets are unfiltered.
    - Use .unscoped() to explicitly bypass the auto-filter.
    - Use .for_organization(org) for explicit filtering in services.
    """

    _auto_scope = True  # Set to False on the unscoped manager

    def get_queryset(self):
        qs = TenantQuerySet(self.model, using=self._db)

        if not self._auto_scope:
            return qs

        org = get_current_organization()
        if org is not None:
            qs = qs.filter(organization=org)

        return qs

    def for_organization(self, organization):
        """Explicit org filter — always works regardless of context."""
        return self.get_queryset().for_organization(organization)

    def unscoped(self):
        """
        Return a queryset that bypasses the automatic tenant filter.

        Use sparingly — platform admin, data migrations, cross-tenant
        reporting only.
        """
        return TenantQuerySet(self.model, using=self._db)


class UnscopedTenantManager(TenantManager):
    """
    Manager that never auto-filters by tenant.

    Assign as Model.unscoped_objects for explicit bypass access:
        Location.unscoped_objects.all()  # all orgs
    """

    _auto_scope = False
