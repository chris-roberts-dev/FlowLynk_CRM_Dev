"""
Tests for apps.common.tenancy.scoping — RBAC scope-based visibility.

Validates:
- ALL_ORG scope: sees everything in the org
- REGION scope: sees only items in assigned region
- MARKET scope: sees only items in assigned market
- LOCATION scope: sees only items in assigned location
- SELF_ASSIGNED scope: falls through correctly when model has no assigned_to field
- Scope fallthrough: if model doesn't support the resolved level, narrows down
- No scope rules: member sees everything (permissive default)
- Superuser bypass: always sees everything
- Cross-model hierarchy: Region, Market, Location each filter correctly
"""

import pytest

from apps.common.tenancy.scoping import apply_scope
from apps.crm.locations.models import Location, Market, Region
from apps.platform.accounts.models import MembershipStatus
from apps.platform.organizations.models import OrganizationStatus
from apps.platform.rbac.models import (
    Capability,
    MembershipRole,
    Role,
    ScopeLevel,
    ScopeRule,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────
@pytest.fixture
def org(make_organization):
    return make_organization(slug="acme", status=OrganizationStatus.ACTIVE)


@pytest.fixture
def hierarchy(org):
    """
    Create two regions with markets and locations:
        SE (Southeast)
            ATL (Atlanta)
                ATL-001 (Atlanta North)
                ATL-002 (Atlanta South)
            ORL (Orlando)
                ORL-001 (Orlando West)
        NE (Northeast)
            NYC (New York City)
                NYC-001 (Manhattan)
    """
    se = Region.unscoped_objects.create(organization=org, code="SE", name="Southeast")
    ne = Region.unscoped_objects.create(organization=org, code="NE", name="Northeast")

    atl = Market.unscoped_objects.create(
        organization=org, code="ATL", name="Atlanta", region=se
    )
    orl = Market.unscoped_objects.create(
        organization=org, code="ORL", name="Orlando", region=se
    )
    nyc = Market.unscoped_objects.create(
        organization=org, code="NYC", name="New York City", region=ne
    )

    atl1 = Location.unscoped_objects.create(
        organization=org, code="ATL-001", name="Atlanta North", market=atl
    )
    atl2 = Location.unscoped_objects.create(
        organization=org, code="ATL-002", name="Atlanta South", market=atl
    )
    orl1 = Location.unscoped_objects.create(
        organization=org, code="ORL-001", name="Orlando West", market=orl
    )
    nyc1 = Location.unscoped_objects.create(
        organization=org, code="NYC-001", name="Manhattan", market=nyc
    )

    return {
        "se": se,
        "ne": ne,
        "atl": atl,
        "orl": orl,
        "nyc": nyc,
        "atl1": atl1,
        "atl2": atl2,
        "orl1": orl1,
        "nyc1": nyc1,
    }


def _make_member_with_scope(
    make_user, make_membership, org, scope_level, **assignments
):
    """Create a membership with a role and scope rule at the given level."""
    user = make_user()
    membership = make_membership(user=user, organization=org)

    # Set geographic assignments
    for attr, value in assignments.items():
        setattr(membership, attr, value)
    membership.save()

    # Create role + scope rule
    role = Role.objects.create(
        organization=org, code=f"role_{user.pk}", name=f"Role {user.pk}"
    )
    ScopeRule.objects.create(role=role, applies_to="*", scope_level=scope_level)
    MembershipRole.objects.create(membership=membership, role=role)

    return membership


# ──────────────────────────────────────────────
# ALL_ORG scope (Owner)
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestAllOrgScope:

    def test_sees_all_locations(self, org, hierarchy, make_user, make_membership):
        member = _make_member_with_scope(
            make_user, make_membership, org, ScopeLevel.ALL_ORG
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 4

    def test_sees_all_regions(self, org, hierarchy, make_user, make_membership):
        member = _make_member_with_scope(
            make_user, make_membership, org, ScopeLevel.ALL_ORG
        )
        qs = Region.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Region)
        assert result.count() == 2

    def test_sees_all_markets(self, org, hierarchy, make_user, make_membership):
        member = _make_member_with_scope(
            make_user, make_membership, org, ScopeLevel.ALL_ORG
        )
        qs = Market.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Market)
        assert result.count() == 3


# ──────────────────────────────────────────────
# REGION scope (Regional Manager)
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestRegionScope:

    def test_sees_only_assigned_region(
        self, org, hierarchy, make_user, make_membership
    ):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.REGION,
            assigned_region=hierarchy["se"],
        )
        qs = Region.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Region)
        assert result.count() == 1
        assert result.first().code == "SE"

    def test_sees_markets_in_region(self, org, hierarchy, make_user, make_membership):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.REGION,
            assigned_region=hierarchy["se"],
        )
        qs = Market.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Market)
        assert result.count() == 2
        codes = set(result.values_list("code", flat=True))
        assert codes == {"ATL", "ORL"}

    def test_sees_locations_in_region(self, org, hierarchy, make_user, make_membership):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.REGION,
            assigned_region=hierarchy["se"],
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 3
        codes = set(result.values_list("code", flat=True))
        assert codes == {"ATL-001", "ATL-002", "ORL-001"}

    def test_cannot_see_other_region(self, org, hierarchy, make_user, make_membership):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.REGION,
            assigned_region=hierarchy["ne"],
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 1
        assert result.first().code == "NYC-001"


# ──────────────────────────────────────────────
# MARKET scope (Market Manager)
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestMarketScope:

    def test_sees_only_assigned_market(
        self, org, hierarchy, make_user, make_membership
    ):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.MARKET,
            assigned_market=hierarchy["atl"],
        )
        qs = Market.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Market)
        assert result.count() == 1
        assert result.first().code == "ATL"

    def test_sees_locations_in_market(self, org, hierarchy, make_user, make_membership):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.MARKET,
            assigned_market=hierarchy["atl"],
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 2
        codes = set(result.values_list("code", flat=True))
        assert codes == {"ATL-001", "ATL-002"}

    def test_cannot_see_other_market_locations(
        self, org, hierarchy, make_user, make_membership
    ):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.MARKET,
            assigned_market=hierarchy["atl"],
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        codes = set(result.values_list("code", flat=True))
        assert "ORL-001" not in codes
        assert "NYC-001" not in codes

    def test_region_view_falls_through_to_market(
        self, org, hierarchy, make_user, make_membership
    ):
        """
        Market-scoped user viewing Regions: Region only declares scope_field_region.
        MARKET level has no match on Region → falls through to LOCATION → SELF_ASSIGNED → none.
        Region model doesn't support MARKET scope, so market managers can't see regions.
        """
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.MARKET,
            assigned_market=hierarchy["atl"],
        )
        qs = Region.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Region)
        # Region only has scope_field_region, not scope_field_market,
        # so MARKET scope falls through and finds nothing applicable.
        assert result.count() == 0


# ──────────────────────────────────────────────
# LOCATION scope (Location Manager)
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLocationScope:

    def test_sees_only_assigned_location(
        self, org, hierarchy, make_user, make_membership
    ):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.LOCATION,
            default_location=hierarchy["atl1"],
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 1
        assert result.first().code == "ATL-001"

    def test_cannot_see_other_locations(
        self, org, hierarchy, make_user, make_membership
    ):
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.LOCATION,
            default_location=hierarchy["atl1"],
        )
        qs = Location.unscoped_objects.filter(organization=org)
        codes = set(apply_scope(qs, member, Location).values_list("code", flat=True))
        assert codes == {"ATL-001"}


# ──────────────────────────────────────────────
# No scope rules (default behavior)
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestNoScopeRules:

    def test_member_without_scope_rules_defaults_to_self_assigned(
        self, org, hierarchy, make_user, make_membership
    ):
        """
        Member with no roles/scope rules gets SELF_ASSIGNED from get_scope().
        Location has no scope_field_assigned_to, so fallthrough yields none().
        """
        user = make_user()
        member = make_membership(user=user, organization=org)

        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 0

    def test_member_with_role_but_no_scope_rule_defaults(
        self, org, hierarchy, make_user, make_membership
    ):
        """Role without any ScopeRule → get_scope returns SELF_ASSIGNED."""
        user = make_user()
        member = make_membership(user=user, organization=org)
        role = Role.objects.create(organization=org, code="norules", name="No Rules")
        MembershipRole.objects.create(membership=member, role=role)

        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 0


# ──────────────────────────────────────────────
# Superuser bypass
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestSuperuserBypass:

    def test_unsaved_membership_gets_all(self, org, hierarchy):
        """Superuser stand-in (pk=None) should see everything."""
        from apps.platform.accounts.models import Membership, MembershipStatus

        standin = Membership(
            user_id=1, organization=org, status=MembershipStatus.ACTIVE
        )
        # pk is None — unsaved stand-in

        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, standin, Location)
        assert result.count() == 4


# ──────────────────────────────────────────────
# None membership
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestNoneMembership:

    def test_none_returns_empty(self, org, hierarchy):
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, None, Location)
        assert result.count() == 0


# ──────────────────────────────────────────────
# Broadest scope wins across multiple roles
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestMultiRoleScope:

    def test_broadest_scope_wins(self, org, hierarchy, make_user, make_membership):
        """Member with both REGION and LOCATION roles → REGION wins."""
        user = make_user()
        member = make_membership(user=user, organization=org)
        member.assigned_region = hierarchy["se"]
        member.default_location = hierarchy["atl1"]
        member.save()

        role_region = Role.objects.create(
            organization=org, code="reg_mgr", name="Regional"
        )
        ScopeRule.objects.create(
            role=role_region, applies_to="*", scope_level=ScopeLevel.REGION
        )
        MembershipRole.objects.create(membership=member, role=role_region)

        role_loc = Role.objects.create(
            organization=org, code="loc_mgr", name="Location"
        )
        ScopeRule.objects.create(
            role=role_loc, applies_to="*", scope_level=ScopeLevel.LOCATION
        )
        MembershipRole.objects.create(membership=member, role=role_loc)

        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        # REGION is broader → sees all SE locations
        assert result.count() == 3


# ──────────────────────────────────────────────
# Missing geographic assignment
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestMissingAssignment:

    def test_region_scope_without_assignment_falls_through(
        self, org, hierarchy, make_user, make_membership
    ):
        """
        REGION scope but no assigned_region → filter value is None → skip.
        Falls through to MARKET (no assigned_market) → LOCATION → SELF_ASSIGNED → none.
        """
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.REGION,
            # No assigned_region set
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 0

    def test_market_scope_with_market_but_no_region(
        self, org, hierarchy, make_user, make_membership
    ):
        """MARKET scope with assigned_market → works fine, doesn't need region."""
        member = _make_member_with_scope(
            make_user,
            make_membership,
            org,
            ScopeLevel.MARKET,
            assigned_market=hierarchy["atl"],
        )
        qs = Location.unscoped_objects.filter(organization=org)
        result = apply_scope(qs, member, Location)
        assert result.count() == 2
