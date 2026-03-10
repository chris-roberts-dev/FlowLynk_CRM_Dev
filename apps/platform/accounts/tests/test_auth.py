"""
Tests for apps.platform.accounts — EPIC 2 auth flows.

Validates:
- Login form renders on base domain
- Successful login with single membership → redirect to org subdomain
- Successful login with multiple memberships → redirect to org picker
- Successful login with no memberships (regular user) → error
- Successful login with no memberships (superuser) → base admin
- Invalid credentials → error shown
- Org picker shows all active orgs
- Org selection validates membership and redirects
- Org selection records last_login_at
- Logout clears session and redirects to base domain
- Unauthenticated access to picker → redirect to login
"""
import pytest
from django.test import Client

from apps.platform.accounts.models import Membership, MembershipStatus
from apps.platform.organizations.models import OrganizationStatus


@pytest.fixture(autouse=True)
def _platform_settings(settings):
    settings.PLATFORM_BASE_DOMAIN = "lvh.me"
    settings.PLATFORM_PORT = "8000"


@pytest.fixture
def active_org(make_organization):
    return make_organization(slug="acme", status=OrganizationStatus.ACTIVE)


@pytest.fixture
def active_user(make_user):
    user = make_user(email="alice@acme.com")
    user.set_password("goodpass123")
    user.save()
    return user


@pytest.fixture
def superuser(make_user):
    su = make_user(email="admin@flowlynk.com")
    su.set_password("superpass123")
    su.is_staff = True
    su.is_superuser = True
    su.save()
    return su


# ──────────────────────────────────────────────
# Login page rendering
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLoginPage:

    def test_login_page_renders(self):
        client = Client()
        response = client.get("/auth/login/", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        assert b"Sign in" in response.content

    def test_login_page_has_email_field(self):
        client = Client()
        response = client.get("/auth/login/", HTTP_HOST="lvh.me:8000")
        assert b'name="email"' in response.content

    def test_login_page_has_password_field(self):
        client = Client()
        response = client.get("/auth/login/", HTTP_HOST="lvh.me:8000")
        assert b'name="password"' in response.content


# ──────────────────────────────────────────────
# Login with single membership
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLoginSingleMembership:

    def test_redirects_to_org_subdomain(self, active_user, active_org, make_membership):
        make_membership(user=active_user, organization=active_org)
        client = Client()

        response = client.post(
            "/auth/login/",
            {"email": "alice@acme.com", "password": "goodpass123"},
            HTTP_HOST="lvh.me:8000",
        )

        assert response.status_code == 302
        assert "acme.lvh.me:8000" in response.url
        assert "/admin/" in response.url

    def test_records_last_login(self, active_user, active_org, make_membership):
        membership = make_membership(user=active_user, organization=active_org)
        assert membership.last_login_at is None

        client = Client()
        client.post(
            "/auth/login/",
            {"email": "alice@acme.com", "password": "goodpass123"},
            HTTP_HOST="lvh.me:8000",
        )

        membership.refresh_from_db()
        assert membership.last_login_at is not None


# ──────────────────────────────────────────────
# Login with multiple memberships
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLoginMultipleMemberships:

    def test_redirects_to_org_picker(
        self, active_user, active_org, make_organization, make_membership
    ):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        make_membership(user=active_user, organization=active_org)
        make_membership(user=active_user, organization=org_b)

        client = Client()
        response = client.post(
            "/auth/login/",
            {"email": "alice@acme.com", "password": "goodpass123"},
            HTTP_HOST="lvh.me:8000",
        )

        assert response.status_code == 302
        assert response.url == "/auth/select-org/"


# ──────────────────────────────────────────────
# Login with no memberships
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLoginNoMembership:

    def test_regular_user_no_membership_gets_error(self, active_user):
        client = Client()
        response = client.post(
            "/auth/login/",
            {"email": "alice@acme.com", "password": "goodpass123"},
            HTTP_HOST="lvh.me:8000",
        )

        assert response.status_code == 302
        assert "error=no_membership" in response.url

    def test_regular_user_no_membership_is_logged_out(self, active_user):
        """User should not remain authenticated after no-membership redirect."""
        client = Client()
        client.post(
            "/auth/login/",
            {"email": "alice@acme.com", "password": "goodpass123"},
            HTTP_HOST="lvh.me:8000",
        )

        # Try accessing a protected page — should not be authenticated
        response = client.get("/auth/select-org/", HTTP_HOST="lvh.me:8000")
        # Should redirect to login (not show the picker)
        assert response.status_code == 302
        assert "login" in response.url

    def test_superuser_no_membership_goes_to_admin(self, superuser):
        client = Client()
        response = client.post(
            "/auth/login/",
            {"email": "admin@flowlynk.com", "password": "superpass123"},
            HTTP_HOST="lvh.me:8000",
        )

        assert response.status_code == 302
        assert response.url == "/admin/"


# ──────────────────────────────────────────────
# Invalid credentials
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLoginInvalidCredentials:

    def test_wrong_password_shows_error(self, active_user):
        client = Client()
        response = client.post(
            "/auth/login/",
            {"email": "alice@acme.com", "password": "wrongpass"},
            HTTP_HOST="lvh.me:8000",
        )

        assert response.status_code == 200  # re-renders form
        assert b"Invalid email or password" in response.content

    def test_nonexistent_email_shows_error(self):
        client = Client()
        response = client.post(
            "/auth/login/",
            {"email": "nobody@nowhere.com", "password": "anything"},
            HTTP_HOST="lvh.me:8000",
        )

        assert response.status_code == 200
        assert b"Invalid email or password" in response.content

    def test_empty_form_shows_errors(self):
        client = Client()
        response = client.post(
            "/auth/login/",
            {"email": "", "password": ""},
            HTTP_HOST="lvh.me:8000",
        )

        assert response.status_code == 200


# ──────────────────────────────────────────────
# Already authenticated user visiting login
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLoginAlreadyAuthenticated:

    def test_authenticated_user_with_single_org_redirected(
        self, active_user, active_org, make_membership
    ):
        make_membership(user=active_user, organization=active_org)
        client = Client()
        client.force_login(active_user)

        response = client.get("/auth/login/", HTTP_HOST="lvh.me:8000")

        assert response.status_code == 302
        assert "acme.lvh.me" in response.url


# ──────────────────────────────────────────────
# Org picker
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestOrgPicker:

    def test_picker_shows_all_active_orgs(
        self, active_user, active_org, make_organization, make_membership
    ):
        org_b = make_organization(slug="beta", name="Beta Corp", status=OrganizationStatus.ACTIVE)
        make_membership(user=active_user, organization=active_org)
        make_membership(user=active_user, organization=org_b)

        client = Client()
        client.force_login(active_user)

        response = client.get("/auth/select-org/", HTTP_HOST="lvh.me:8000")

        assert response.status_code == 200
        assert b"acme" in response.content
        assert b"Beta Corp" in response.content

    def test_picker_excludes_inactive_memberships(
        self, active_user, active_org, make_organization, make_membership
    ):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        make_membership(user=active_user, organization=active_org)
        make_membership(
            user=active_user, organization=org_b, status=MembershipStatus.INACTIVE
        )

        client = Client()
        client.force_login(active_user)

        response = client.get("/auth/select-org/", HTTP_HOST="lvh.me:8000")

        assert response.status_code == 200
        assert b"acme" in response.content
        assert b"beta" not in response.content

    def test_unauthenticated_picker_redirects_to_login(self):
        client = Client()
        response = client.get("/auth/select-org/", HTTP_HOST="lvh.me:8000")

        assert response.status_code == 302
        assert "login" in response.url


# ──────────────────────────────────────────────
# Org selection
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestSelectOrg:

    def test_valid_selection_redirects_to_subdomain(
        self, active_user, active_org, make_membership
    ):
        make_membership(user=active_user, organization=active_org)
        client = Client()
        client.force_login(active_user)

        response = client.get(
            "/auth/select-org/acme/", HTTP_HOST="lvh.me:8000"
        )

        assert response.status_code == 302
        assert "acme.lvh.me:8000" in response.url

    def test_selection_records_last_login(
        self, active_user, active_org, make_membership
    ):
        membership = make_membership(user=active_user, organization=active_org)
        client = Client()
        client.force_login(active_user)

        client.get("/auth/select-org/acme/", HTTP_HOST="lvh.me:8000")

        membership.refresh_from_db()
        assert membership.last_login_at is not None

    def test_invalid_org_slug_redirects_to_picker(
        self, active_user, active_org, make_membership
    ):
        make_membership(user=active_user, organization=active_org)
        client = Client()
        client.force_login(active_user)

        response = client.get(
            "/auth/select-org/nonexistent/", HTTP_HOST="lvh.me:8000"
        )

        assert response.status_code == 302
        assert "select-org" in response.url

    def test_no_membership_in_org_redirects_to_picker(
        self, active_user, active_org, make_organization, make_membership
    ):
        """User has membership in acme but tries to select beta."""
        make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        make_membership(user=active_user, organization=active_org)
        client = Client()
        client.force_login(active_user)

        response = client.get(
            "/auth/select-org/beta/", HTTP_HOST="lvh.me:8000"
        )

        assert response.status_code == 302
        # Should go back to picker, not to beta
        assert "beta.lvh.me" not in response.url

    def test_unauthenticated_selection_redirects_to_login(self):
        client = Client()
        response = client.get(
            "/auth/select-org/acme/", HTTP_HOST="lvh.me:8000"
        )

        assert response.status_code == 302
        assert "login" in response.url


# ──────────────────────────────────────────────
# Logout
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLogout:

    def test_logout_redirects_to_base_domain(self, active_user):
        client = Client()
        client.force_login(active_user)

        response = client.get("/auth/logout/", HTTP_HOST="lvh.me:8000")

        assert response.status_code == 302
        assert "lvh.me:8000" in response.url
        # Should NOT contain any org subdomain
        assert response.url.startswith("http://lvh.me:8000/")

    def test_logout_clears_session(self, active_user):
        client = Client()
        client.force_login(active_user)

        client.get("/auth/logout/", HTTP_HOST="lvh.me:8000")

        # Verify session is cleared — try accessing picker
        response = client.get("/auth/select-org/", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 302
        assert "login" in response.url

    def test_logout_via_post(self, active_user):
        """POST logout should also work (CSRF-protected forms)."""
        client = Client()
        client.force_login(active_user)

        response = client.post("/auth/logout/", HTTP_HOST="lvh.me:8000")

        assert response.status_code == 302
        assert "lvh.me:8000" in response.url

    def test_unauthenticated_logout_still_redirects(self):
        """Hitting logout when not logged in should not crash."""
        client = Client()
        response = client.get("/auth/logout/", HTTP_HOST="lvh.me:8000")

        assert response.status_code == 302


# ──────────────────────────────────────────────
# Services
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestAuthServices:

    def test_build_org_admin_url(self, settings):
        from apps.platform.accounts.services import build_org_admin_url

        settings.PLATFORM_BASE_DOMAIN = "lvh.me"
        settings.PLATFORM_PORT = "8000"
        assert build_org_admin_url("acme") == "http://acme.lvh.me:8000/admin/"

    def test_build_org_admin_url_no_port(self, settings):
        from apps.platform.accounts.services import build_org_admin_url

        settings.PLATFORM_BASE_DOMAIN = "flowlynk.com"
        settings.PLATFORM_PORT = ""
        assert build_org_admin_url("acme") == "http://acme.flowlynk.com/admin/"

    def test_build_base_url(self, settings):
        from apps.platform.accounts.services import build_base_url

        settings.PLATFORM_BASE_DOMAIN = "lvh.me"
        settings.PLATFORM_PORT = "8000"
        assert build_base_url() == "http://lvh.me:8000/"

    def test_get_active_memberships(
        self, active_user, active_org, make_organization, make_membership
    ):
        from apps.platform.accounts.services import get_active_memberships

        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        make_membership(user=active_user, organization=active_org)
        make_membership(
            user=active_user, organization=org_b, status=MembershipStatus.INACTIVE
        )

        result = list(get_active_memberships(active_user))
        assert len(result) == 1
        assert result[0].organization == active_org

    def test_record_login(self, active_user, active_org, make_membership):
        from apps.platform.accounts.services import record_login

        membership = make_membership(user=active_user, organization=active_org)
        assert membership.last_login_at is None

        record_login(membership)
        membership.refresh_from_db()
        assert membership.last_login_at is not None
