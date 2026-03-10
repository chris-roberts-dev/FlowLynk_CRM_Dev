"""
apps.platform.accounts.services — Account service layer.

Provides helpers used by views and (later) API endpoints.
The heavy auth flow logic lives in the views for EPIC 2 since it's
tightly coupled to request/response. This service handles reusable
membership queries and URL building.
"""
import logging

from django.conf import settings
from django.utils import timezone

from apps.platform.accounts.models import Membership, MembershipStatus

logger = logging.getLogger(__name__)


def get_active_memberships(user):
    """
    Return a queryset of the user's active memberships with org data.

    Used by login and org picker views to decide routing.
    """
    return (
        Membership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        )
        .select_related("organization")
        .order_by("organization__name")
    )


def build_org_admin_url(org_slug: str) -> str:
    """
    Build the absolute URL to an org's admin panel.

    Examples:
        build_org_admin_url("acme") → "http://acme.lvh.me:8000/admin/"
    """
    base_domain = settings.PLATFORM_BASE_DOMAIN
    port = settings.PLATFORM_PORT
    scheme = "http"  # EPIC 15 adds HTTPS detection

    if port:
        return f"{scheme}://{org_slug}.{base_domain}:{port}/admin/"
    return f"{scheme}://{org_slug}.{base_domain}/admin/"


def build_base_url() -> str:
    """Build the absolute URL to the base domain landing page."""
    base_domain = settings.PLATFORM_BASE_DOMAIN
    port = settings.PLATFORM_PORT
    scheme = "http"

    if port:
        return f"{scheme}://{base_domain}:{port}/"
    return f"{scheme}://{base_domain}/"


def record_login(membership):
    """Update last_login_at on a membership after org selection."""
    membership.last_login_at = timezone.now()
    membership.save(update_fields=["last_login_at"])
    logger.info(
        "Membership login recorded: user '%s' in org '%s'",
        membership.user.email,
        membership.organization.slug,
        extra={
            "user_id": membership.user.pk,
            "org_id": membership.organization.pk,
            "membership_id": membership.pk,
        },
    )
