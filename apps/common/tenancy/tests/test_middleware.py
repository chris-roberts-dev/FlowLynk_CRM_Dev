"""
Tests for apps.common.tenancy.middleware — TenantMiddleware.

Validates:
- Subdomain extraction from Host header
- Base domain requests pass through with no tenant context
- Invalid subdomain redirects to base with ?error=invalid_org
- Suspended org redirects to base with ?error=org_suspended
- Unauthenticated user on valid subdomain → redirect with ?error=login_required
- Authenticated user with no membership → redirect with ?error=no_membership
- Authenticated user with active membership → org + membership set
- Superuser can access any org (impersonation)
"""

import pytest
from django.test import RequestFactory

from apps.common.tenancy.context import get_current_organization, get_current_membership
from apps.common.tenancy.middleware import TenantMiddleware
from apps.platform.accounts.models import MembershipStatus
from apps.platform.organizations.models import OrganizationStatus


# ──────────────────────────────────────────────
# Shared fixture: pin platform settings for all tests in this file
# ──────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _platform_settings(settings):
    """Ensure consistent platform domain config for middleware tests."""
    settings.PLATFORM_BASE_DOMAIN = "lvh.me"
    settings.PLATFORM_PORT = "8000"


# ──────────────────────────────────────────────
# Subdomain extraction (unit tests — no DB needed)
# ──────────────────────────────────────────────
class TestSubdomainExtraction:
    """Tests for TenantMiddleware._extract_subdomain (static method)."""

    def test_base_domain_returns_none(self):
        assert TenantMiddleware._extract_subdomain("lvh.me", "lvh.me") is None

    def test_valid_subdomain(self):
        assert TenantMiddleware._extract_subdomain("acme.lvh.me", "lvh.me") == "acme"

    def test_subdomain_lowercased(self):
        assert TenantMiddleware._extract_subdomain("ACME.lvh.me", "lvh.me") == "acme"

    def test_multi_level_subdomain_rejected(self):
        """Only single-level subdomains are valid tenant slugs."""
        assert TenantMiddleware._extract_subdomain("deep.sub.lvh.me", "lvh.me") is None

    def test_localhost_returns_none(self):
        assert TenantMiddleware._extract_subdomain("localhost", "lvh.me") is None

    def test_ip_address_returns_none(self):
        assert TenantMiddleware._extract_subdomain("127.0.0.1", "lvh.me") is None

    def test_unrelated_domain_returns_none(self):
        assert TenantMiddleware._extract_subdomain("acme.other.com", "lvh.me") is None

    def test_empty_prefix_returns_none(self):
        """Edge case: '.lvh.me' with empty prefix."""
        assert TenantMiddleware._extract_subdomain(".lvh.me", "lvh.me") is None

    def test_production_domain(self):
        assert (
            TenantMiddleware._extract_subdomain("acme.flowlynk.com", "flowlynk.com")
            == "acme"
        )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def _make_get_response():
    """Dummy get_response that returns a 200."""
    from django.http import HttpResponse

    def get_response(request):
        return HttpResponse("OK", status=200)

    return get_response


def _build_request(host, user=None, path="/"):
    """Build a fake request with the given host and optional user."""
    from django.contrib.auth.models import AnonymousUser

    factory = RequestFactory()
    request = factory.get(path, HTTP_HOST=host)
    request.user = user if user is not None else AnonymousUser()
    request.session = {}
    return request


# ──────────────────────────────────────────────
# Middleware integration tests (require DB)
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestMiddlewareBaseDomain:
    """Requests to the base domain should pass through with no tenant context."""

    def test_base_domain_sets_no_organization(self):
        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("lvh.me:8000")

        response = middleware(request)

        assert request.organization is None
        assert request.membership is None
        assert response.status_code == 200

    def test_localhost_redirects_to_base_domain(self):
        """localhost should redirect to lvh.me so sessions work correctly."""
        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("localhost:8000")

        response = middleware(request)

        assert response.status_code == 302
        assert "lvh.me:8000" in response.url


@pytest.mark.django_db
class TestMiddlewareInvalidOrg:
    """Invalid subdomain should redirect to base with ?error=invalid_org."""

    def test_unknown_slug_redirects(self):
        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("nonexistent.lvh.me:8000")

        response = middleware(request)

        assert response.status_code == 302
        assert "error=invalid_org" in response.url


@pytest.mark.django_db
class TestMiddlewareSuspendedOrg:
    """Suspended org should redirect to base with ?error=org_suspended."""

    def test_suspended_org_redirects(self, make_organization):
        make_organization(slug="suspended-co", status=OrganizationStatus.SUSPENDED)
        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("suspended-co.lvh.me:8000")

        response = middleware(request)

        assert response.status_code == 302
        assert "error=org_suspended" in response.url


@pytest.mark.django_db
class TestMiddlewareUnauthenticated:
    """Unauthenticated user on valid tenant subdomain → redirect to base."""

    def test_unauthenticated_redirects(self, make_organization):
        make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000")

        response = middleware(request)

        assert response.status_code == 302
        assert "error=login_required" in response.url

    def test_static_paths_exempt_from_redirect(self, make_organization):
        """Static file paths should not trigger auth redirect."""
        make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000", path="/static/css/style.css")

        response = middleware(request)

        assert response.status_code == 200


@pytest.mark.django_db
class TestMiddlewareNoMembership:
    """Authenticated user with no membership → redirect with ?error=no_membership."""

    def test_no_membership_redirects(self, make_organization, make_user):
        make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        user = make_user()
        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000", user=user)

        response = middleware(request)

        assert response.status_code == 302
        assert "error=no_membership" in response.url

    def test_inactive_membership_redirects(
        self, make_organization, make_user, make_membership
    ):
        org = make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        user = make_user()
        make_membership(user=user, organization=org, status=MembershipStatus.INACTIVE)

        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000", user=user)

        response = middleware(request)

        assert response.status_code == 302
        assert "error=no_membership" in response.url


@pytest.mark.django_db
class TestMiddlewareHappyPath:
    """Authenticated user with active membership → org + membership set."""

    def test_valid_tenant_sets_context(
        self, make_organization, make_user, make_membership
    ):
        org = make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        user = make_user()
        membership = make_membership(user=user, organization=org)

        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000", user=user)

        response = middleware(request)

        assert response.status_code == 200
        assert request.organization == org
        assert request.membership == membership

    def test_trial_org_is_accessible(
        self, make_organization, make_user, make_membership
    ):
        """TRIAL status orgs should be accessible (only SUSPENDED is blocked)."""
        org = make_organization(slug="trial-co", status=OrganizationStatus.TRIAL)
        user = make_user()
        make_membership(user=user, organization=org)

        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("trial-co.lvh.me:8000", user=user)

        response = middleware(request)

        assert response.status_code == 200
        assert request.organization == org


@pytest.mark.django_db
class TestMiddlewareSuperuser:
    """Superusers can access any org, even without a real membership."""

    def test_superuser_with_membership(
        self, make_organization, make_user, make_membership
    ):
        org = make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        su = make_user(email="super@test.com")
        su.is_superuser = True
        su.is_staff = True
        su.save()
        membership = make_membership(user=su, organization=org)

        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000", user=su)

        response = middleware(request)

        assert response.status_code == 200
        assert request.organization == org
        assert request.membership == membership

    def test_superuser_without_membership_gets_standin(
        self, make_organization, make_user
    ):
        org = make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        su = make_user(email="super-no-member@test.com")
        su.is_superuser = True
        su.is_staff = True
        su.save()

        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000", user=su)

        response = middleware(request)

        assert response.status_code == 200
        assert request.organization == org
        assert request.membership is not None
        assert request.membership.pk is None
        assert request.membership.user == su
        assert request.membership.organization == org


@pytest.mark.django_db
class TestMiddlewareClearsContext:
    """Context vars are cleared after every request."""

    def test_context_cleared_after_response(
        self, make_organization, make_user, make_membership
    ):
        org = make_organization(slug="acme", status=OrganizationStatus.ACTIVE)
        user = make_user()
        make_membership(user=user, organization=org)

        middleware = TenantMiddleware(_make_get_response())
        request = _build_request("acme.lvh.me:8000", user=user)

        middleware(request)

        assert get_current_organization() is None
        assert get_current_membership() is None
