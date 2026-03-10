"""
apps.common.tenancy.middleware — Tenant resolution middleware.

Resolution flow:
1. Extract subdomain from Host header
2. No subdomain (base domain) → public context, proceed
3. Subdomain found → lookup Organization by slug
   a. Not found → redirect to base domain with ?error=invalid_org
   b. Found but SUSPENDED → redirect to base domain with ?error=org_suspended
   c. Found and valid → set request.organization
      - User not authenticated → redirect to base domain with ?next= for login
      - User authenticated → lookup active Membership for (user, org)
        * No active membership → redirect to base domain with ?error=no_membership
        * Has membership → set request.membership, proceed

Thread-local context is set so TenantManager can auto-filter querysets.

Exempt paths:
- /admin/login/ (Django admin login must be accessible)
- /static/ (static files)
"""

import logging

from django.conf import settings
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from apps.common.tenancy.context import (
    clear_tenant_context,
    set_current_membership,
    set_current_organization,
)

logger = logging.getLogger(__name__)

# Paths that skip tenant enforcement (still resolve org for context,
# but don't redirect unauthenticated users).
EXEMPT_PATH_PREFIXES = (
    "/static/",
    "/favicon.ico",
)


class TenantMiddleware(MiddlewareMixin):
    """
    Resolves the current tenant from the request Host header subdomain.

    Sets on every request:
        request.organization  — Organization instance or None (base domain)
        request.membership    — Membership instance or None

    Also populates thread-local context for TenantManager auto-filtering.
    """

    def process_request(self, request):
        # Always initialize to None
        request.organization = None
        request.membership = None

        # Extract subdomain
        host = request.get_host().split(":")[0]  # strip port
        base_domain = settings.PLATFORM_BASE_DOMAIN

        # Redirect localhost / 127.0.0.1 to the platform base domain.
        # Session cookies won't transfer across domains, so all auth
        # must happen on the base domain (lvh.me in dev).
        if host in ("localhost", "127.0.0.1") and base_domain != host:
            return self._redirect_to_base()

        subdomain = self._extract_subdomain(host, base_domain)

        if not subdomain:
            # Base domain — public context (landing page, login, etc.)
            set_current_organization(None)
            set_current_membership(None)
            return None  # proceed normally

        # Subdomain present — resolve organization
        from apps.platform.organizations.models import Organization

        try:
            org = Organization.objects.get(slug=subdomain)
        except Organization.DoesNotExist:
            logger.warning(
                "Tenant resolution failed: unknown slug '%s'",
                subdomain,
                extra={"subdomain": subdomain, "host": host},
            )
            return self._redirect_to_base("invalid_org")

        # Check org status
        if org.is_suspended:
            logger.warning(
                "Tenant resolution blocked: org '%s' is suspended",
                org.slug,
                extra={"org_id": org.pk, "org_slug": org.slug},
            )
            return self._redirect_to_base("org_suspended")

        # Valid org — set on request and context
        request.organization = org
        set_current_organization(org)

        # Skip auth enforcement for exempt paths
        if self._is_exempt(request.path):
            return None

        # Check authentication
        if not request.user.is_authenticated:
            logger.debug(
                "Unauthenticated user on tenant subdomain '%s', redirecting to base",
                subdomain,
            )
            return self._redirect_to_base("login_required")

        # Authenticated — resolve membership
        # Superusers can access any org (impersonation / platform admin)
        if request.user.is_superuser:
            request.membership = self._get_or_fake_superuser_membership(
                request.user, org
            )
            set_current_membership(request.membership)
            return None

        # Regular user — must have active membership
        from apps.platform.accounts.models import Membership, MembershipStatus

        try:
            membership = Membership.objects.select_related("user", "organization").get(
                user=request.user,
                organization=org,
                status=MembershipStatus.ACTIVE,
            )
        except Membership.DoesNotExist:
            logger.warning(
                "User '%s' has no active membership in org '%s'",
                request.user.email,
                org.slug,
                extra={"user_id": request.user.pk, "org_id": org.pk},
            )
            return self._redirect_to_base("no_membership")

        request.membership = membership
        set_current_membership(membership)
        return None  # proceed

    def process_response(self, request, response):
        """Clear thread-local context after every request."""
        clear_tenant_context()
        return response

    # ── Helpers ──────────────────────────────────────

    @staticmethod
    def _extract_subdomain(host: str, base_domain: str) -> str | None:
        """
        Extract subdomain from host, given the platform base domain.

        Examples:
            host='acme.lvh.me', base='lvh.me' → 'acme'
            host='lvh.me', base='lvh.me' → None
            host='localhost', base='lvh.me' → None
            host='deep.sub.lvh.me', base='lvh.me' → None (multi-level rejected)
        """
        if not host.endswith(f".{base_domain}"):
            return None

        # Strip the base domain to get the subdomain portion
        prefix = host[: -(len(base_domain) + 1)]

        # Reject multi-level subdomains (e.g., 'a.b' in 'a.b.lvh.me')
        if not prefix or "." in prefix:
            return None

        return prefix.lower()

    @staticmethod
    def _redirect_to_base(error_code: str = ""):
        """Build redirect to base domain landing page with optional error query param."""
        base_domain = settings.PLATFORM_BASE_DOMAIN
        port = settings.PLATFORM_PORT
        scheme = "http"  # EPIC 15 adds HTTPS detection

        if port:
            base_url = f"{scheme}://{base_domain}:{port}/"
        else:
            base_url = f"{scheme}://{base_domain}/"

        if error_code:
            return redirect(f"{base_url}?error={error_code}")
        return redirect(base_url)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        """Check if the request path is exempt from tenant auth enforcement."""
        return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)

    @staticmethod
    def _get_or_fake_superuser_membership(user, org):
        """
        For superusers, return their real membership if one exists,
        otherwise return a lightweight stand-in so request.membership
        is always set on tenant subdomains.

        The stand-in is NOT saved to the database — it exists only for
        the duration of the request to satisfy code that reads
        request.membership.
        """
        from apps.platform.accounts.models import Membership, MembershipStatus

        try:
            return Membership.objects.get(
                user=user,
                organization=org,
                status=MembershipStatus.ACTIVE,
            )
        except Membership.DoesNotExist:
            # Unsaved stand-in for superuser impersonation
            return Membership(
                user=user,
                organization=org,
                status=MembershipStatus.ACTIVE,
            )
