"""
Root conftest.py — shared fixtures for FlowLynk test suite.

Provides:
- Database access for all tests (via @pytest.mark.django_db or db fixture)
- Organization factory
- User factory
- Membership factory

These fixtures ensure consistent test data across all app test modules.
"""
import pytest

from apps.platform.accounts.models import Membership, MembershipStatus, User
from apps.platform.organizations.models import Organization, OrganizationStatus


# ──────────────────────────────────────────────
# Factory helpers
# ──────────────────────────────────────────────
@pytest.fixture
def make_organization(db):
    """Factory fixture: creates an Organization with sensible defaults."""
    _counter = 0

    def _factory(**kwargs):
        nonlocal _counter
        _counter += 1
        defaults = {
            "name": f"Test Org {_counter}",
            "slug": f"test-org-{_counter}",
        }
        defaults.update(kwargs)
        return Organization.objects.create(**defaults)

    return _factory


@pytest.fixture
def make_user(db):
    """Factory fixture: creates a User with sensible defaults."""
    _counter = 0

    def _factory(**kwargs):
        nonlocal _counter
        _counter += 1
        defaults = {
            "email": f"user{_counter}@test.flowlynk.com",
        }
        defaults.update(kwargs)
        password = defaults.pop("password", "testpass123")
        return User.objects.create_user(password=password, **defaults)

    return _factory


@pytest.fixture
def make_membership(db):
    """Factory fixture: creates a Membership linking a User to an Org."""

    def _factory(user, organization, **kwargs):
        defaults = {
            "status": MembershipStatus.ACTIVE,
        }
        defaults.update(kwargs)
        return Membership.objects.create(
            user=user,
            organization=organization,
            **defaults,
        )

    return _factory


# ──────────────────────────────────────────────
# Convenience combo fixtures
# ──────────────────────────────────────────────
@pytest.fixture
def org(make_organization):
    """A single active Organization for simple tests."""
    return make_organization(status=OrganizationStatus.ACTIVE)


@pytest.fixture
def user(make_user):
    """A single User for simple tests."""
    return make_user()


@pytest.fixture
def membership(user, org, make_membership):
    """A single active Membership (user ↔ org) for simple tests."""
    return make_membership(user=user, organization=org)
