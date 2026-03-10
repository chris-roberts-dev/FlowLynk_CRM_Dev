"""
Tests for apps.common.tenancy.managers — TenantManager auto-scoping.

Validates:
- With context set: only current org's records returned
- Without context: all records returned (management commands, migrations)
- .unscoped() bypasses auto-filter even with context active
- .for_organization() explicit filter always works
- Cross-tenant isolation: Org A cannot see Org B's records
"""
import pytest

from apps.common.tenancy.context import (
    clear_tenant_context,
    set_current_organization,
)
from apps.crm.locations.models import Location
from apps.platform.organizations.models import OrganizationStatus


@pytest.fixture
def two_orgs_with_locations(make_organization):
    """
    Create two orgs, each with two locations. Returns a dict:
    {
        'org_a': Organization,
        'org_b': Organization,
        'loc_a1': Location, 'loc_a2': Location,
        'loc_b1': Location, 'loc_b2': Location,
    }
    """
    org_a = make_organization(slug="org-a", status=OrganizationStatus.ACTIVE)
    org_b = make_organization(slug="org-b", status=OrganizationStatus.ACTIVE)

    loc_a1 = Location.unscoped_objects.create(
        organization=org_a, code="A1", name="Alpha One"
    )
    loc_a2 = Location.unscoped_objects.create(
        organization=org_a, code="A2", name="Alpha Two"
    )
    loc_b1 = Location.unscoped_objects.create(
        organization=org_b, code="B1", name="Bravo One"
    )
    loc_b2 = Location.unscoped_objects.create(
        organization=org_b, code="B2", name="Bravo Two"
    )

    return {
        "org_a": org_a,
        "org_b": org_b,
        "loc_a1": loc_a1,
        "loc_a2": loc_a2,
        "loc_b1": loc_b1,
        "loc_b2": loc_b2,
    }


@pytest.mark.django_db
class TestTenantManagerAutoScoping:
    """TenantManager auto-filters by context var when set."""

    def teardown_method(self):
        """Ensure context is cleared after each test."""
        clear_tenant_context()

    def test_no_context_returns_all(self, two_orgs_with_locations):
        """Without active context, all records are returned."""
        clear_tenant_context()

        all_locations = Location.objects.all()
        assert all_locations.count() == 4

    def test_with_context_returns_only_current_org(self, two_orgs_with_locations):
        """With context set to org_a, only org_a's locations are returned."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        locations = Location.objects.all()
        assert locations.count() == 2
        assert set(locations.values_list("code", flat=True)) == {"A1", "A2"}

    def test_context_switch(self, two_orgs_with_locations):
        """Switching context changes which records are visible."""
        data = two_orgs_with_locations

        set_current_organization(data["org_a"])
        assert Location.objects.count() == 2

        set_current_organization(data["org_b"])
        assert Location.objects.count() == 2
        assert set(Location.objects.values_list("code", flat=True)) == {"B1", "B2"}

    def test_get_by_pk_fails_cross_tenant(self, two_orgs_with_locations):
        """Attempting to get another org's record by PK raises DoesNotExist."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        with pytest.raises(Location.DoesNotExist):
            Location.objects.get(pk=data["loc_b1"].pk)

    def test_filter_by_pk_returns_empty_cross_tenant(self, two_orgs_with_locations):
        """Filtering by another org's PK returns empty queryset."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        result = Location.objects.filter(pk=data["loc_b1"].pk)
        assert result.count() == 0


@pytest.mark.django_db
class TestTenantManagerUnscoped:
    """UnscopedTenantManager and .unscoped() bypass auto-filtering."""

    def teardown_method(self):
        clear_tenant_context()

    def test_unscoped_objects_ignores_context(self, two_orgs_with_locations):
        """unscoped_objects always returns all records."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        all_locations = Location.unscoped_objects.all()
        assert all_locations.count() == 4

    def test_unscoped_method_ignores_context(self, two_orgs_with_locations):
        """objects.unscoped() returns all records even with context."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        all_locations = Location.objects.unscoped()
        assert all_locations.count() == 4


@pytest.mark.django_db
class TestTenantManagerExplicitFilter:
    """.for_organization() provides explicit filtering."""

    def teardown_method(self):
        clear_tenant_context()

    def test_for_organization_filters_correctly(self, two_orgs_with_locations):
        data = two_orgs_with_locations
        clear_tenant_context()

        result = Location.objects.for_organization(data["org_b"])
        assert result.count() == 2
        assert set(result.values_list("code", flat=True)) == {"B1", "B2"}

    def test_for_organization_overrides_context(self, two_orgs_with_locations):
        """
        for_organization() adds an explicit filter ON TOP of the auto-scope.
        If context is org_a and we ask for org_b, we get zero results because
        both filters apply (org_a AND org_b). This is intentional — use
        .unscoped().for_organization() if you need cross-tenant access.
        """
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        # Both auto-scope (org_a) and explicit (org_b) apply → empty
        result = Location.objects.for_organization(data["org_b"])
        assert result.count() == 0

    def test_unscoped_for_organization(self, two_orgs_with_locations):
        """unscoped().for_organization() gives clean explicit access."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        # Bypass auto-scope, then filter explicitly
        result = Location.objects.unscoped().for_organization(data["org_b"])
        assert result.count() == 2
        assert set(result.values_list("code", flat=True)) == {"B1", "B2"}


@pytest.mark.django_db
class TestCrossTenantIsolation:
    """
    Critical isolation tests. These are the core safety guarantees.

    Org A must NEVER be able to read, filter, or access Org B's records
    through the default manager when context is active.
    """

    def teardown_method(self):
        clear_tenant_context()

    def test_org_a_cannot_see_org_b_locations(self, two_orgs_with_locations):
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        visible_codes = set(Location.objects.values_list("code", flat=True))
        assert "B1" not in visible_codes
        assert "B2" not in visible_codes
        assert visible_codes == {"A1", "A2"}

    def test_org_b_cannot_see_org_a_locations(self, two_orgs_with_locations):
        data = two_orgs_with_locations
        set_current_organization(data["org_b"])

        visible_codes = set(Location.objects.values_list("code", flat=True))
        assert "A1" not in visible_codes
        assert "A2" not in visible_codes
        assert visible_codes == {"B1", "B2"}

    def test_cross_tenant_update_impossible(self, two_orgs_with_locations):
        """Bulk update through scoped manager cannot touch other org's records."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        # Try to update ALL visible locations
        Location.objects.all().update(name="HACKED")

        # Org B's records should be untouched
        clear_tenant_context()
        loc_b1 = Location.unscoped_objects.get(pk=data["loc_b1"].pk)
        assert loc_b1.name == "Bravo One"

    def test_cross_tenant_delete_impossible(self, two_orgs_with_locations):
        """Bulk delete through scoped manager cannot touch other org's records."""
        data = two_orgs_with_locations
        set_current_organization(data["org_a"])

        # Delete all visible locations (should only delete org_a's)
        Location.objects.all().delete()

        clear_tenant_context()
        assert Location.unscoped_objects.filter(
            organization=data["org_a"]
        ).count() == 0
        assert Location.unscoped_objects.filter(
            organization=data["org_b"]
        ).count() == 2
