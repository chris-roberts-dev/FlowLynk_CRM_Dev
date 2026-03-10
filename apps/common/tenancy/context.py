"""
apps.common.tenancy.context — Thread-local tenant context.

Stores the current Organization so that TenantManager can auto-filter
querysets without needing an explicit request object.

The middleware sets this on request entry and clears it on exit.
Celery tasks / async jobs should set it explicitly before accessing
tenant-scoped data.

Usage:
    from apps.common.tenancy.context import get_current_organization

    org = get_current_organization()  # returns Organization or None
"""
import contextvars
import threading

# contextvars for async safety; threading.local as fallback reference.
_current_organization: contextvars.ContextVar = contextvars.ContextVar(
    "current_organization", default=None
)
_current_membership: contextvars.ContextVar = contextvars.ContextVar(
    "current_membership", default=None
)


def set_current_organization(organization):
    """Set the active organization for the current context."""
    _current_organization.set(organization)


def get_current_organization():
    """Get the active organization for the current context, or None."""
    return _current_organization.get()


def set_current_membership(membership):
    """Set the active membership for the current context."""
    _current_membership.set(membership)


def get_current_membership():
    """Get the active membership for the current context, or None."""
    return _current_membership.get()


def clear_tenant_context():
    """Clear all tenant context. Called by middleware on response."""
    _current_organization.set(None)
    _current_membership.set(None)
