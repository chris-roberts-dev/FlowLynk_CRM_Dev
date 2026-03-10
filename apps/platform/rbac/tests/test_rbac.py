"""
Tests for apps.platform.rbac — EPIC 3 RBAC.

Validates:
- Capability model CRUD and uniqueness
- Role model CRUD with org-scoped uniqueness
- RoleCapability grants
- MembershipRole assignments
- has_capability() checks
- get_all_capabilities() aggregation
- get_scope() resolution with domain fallback
- require_capability decorator
- Role import from CSV: dry-run, commit, idempotency, error handling
- Seed capabilities command
"""
import pytest

from apps.platform.rbac.models import (
    Capability,
    MembershipRole,
    Role,
    RoleCapability,
    ScopeLevel,
    ScopeRule,
)
from apps.platform.rbac.services import (
    PermissionDenied,
    get_all_capabilities,
    get_scope,
    has_capability,
    import_roles_from_csv,
    require_capability,
)
from apps.platform.organizations.models import OrganizationStatus


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────
@pytest.fixture
def cap_leads_view(db):
    return Capability.objects.create(code="leads.view", description="View leads")


@pytest.fixture
def cap_leads_convert(db):
    return Capability.objects.create(code="leads.convert", description="Convert leads")


@pytest.fixture
def cap_pricing_preview(db):
    return Capability.objects.create(code="pricing.preview", description="Preview pricing")


@pytest.fixture
def cap_inactive(db):
    return Capability.objects.create(code="old.feature", description="Deprecated", is_active=False)


@pytest.fixture
def active_org(make_organization):
    return make_organization(slug="acme", status=OrganizationStatus.ACTIVE)


@pytest.fixture
def role_manager(active_org, cap_leads_view, cap_leads_convert, cap_pricing_preview):
    """A role with three capabilities."""
    role = Role.objects.create(
        organization=active_org, code="office_mgr", name="Office Manager"
    )
    RoleCapability.objects.create(role=role, capability=cap_leads_view)
    RoleCapability.objects.create(role=role, capability=cap_leads_convert)
    RoleCapability.objects.create(role=role, capability=cap_pricing_preview)
    return role


@pytest.fixture
def role_tech(active_org, cap_leads_view):
    """A role with one capability."""
    role = Role.objects.create(
        organization=active_org, code="field_tech", name="Field Tech"
    )
    RoleCapability.objects.create(role=role, capability=cap_leads_view)
    return role


@pytest.fixture
def member_with_role(make_user, active_org, make_membership, role_manager):
    """A membership with the office_mgr role assigned."""
    user = make_user(email="manager@acme.com")
    membership = make_membership(user=user, organization=active_org)
    MembershipRole.objects.create(membership=membership, role=role_manager)
    return membership


@pytest.fixture
def member_no_roles(make_user, active_org, make_membership):
    """A membership with no roles assigned."""
    user = make_user(email="noroles@acme.com")
    return make_membership(user=user, organization=active_org)


# ──────────────────────────────────────────────
# Model tests
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestCapabilityModel:

    def test_create_capability(self, cap_leads_view):
        assert cap_leads_view.pk is not None
        assert cap_leads_view.code == "leads.view"
        assert cap_leads_view.is_active is True

    def test_code_uniqueness(self, cap_leads_view):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Capability.objects.create(code="leads.view")

    def test_str(self, cap_leads_view):
        assert str(cap_leads_view) == "leads.view"

    def test_inactive_capability(self, cap_inactive):
        assert cap_inactive.is_active is False


@pytest.mark.django_db
class TestRoleModel:

    def test_create_role(self, role_manager, active_org):
        assert role_manager.pk is not None
        assert role_manager.organization == active_org
        assert role_manager.code == "office_mgr"

    def test_org_code_uniqueness(self, active_org, role_manager):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            Role.objects.create(
                organization=active_org, code="office_mgr", name="Duplicate"
            )

    def test_same_code_different_orgs(self, active_org, make_organization):
        """Same code is allowed in different orgs."""
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        Role.objects.create(organization=active_org, code="admin", name="Admin A")
        role_b = Role.objects.create(organization=org_b, code="admin", name="Admin B")
        assert role_b.pk is not None

    def test_capabilities_through_relation(self, role_manager):
        cap_codes = set(role_manager.capabilities.values_list("code", flat=True))
        assert cap_codes == {"leads.view", "leads.convert", "pricing.preview"}

    def test_str(self, role_manager):
        assert str(role_manager) == "Office Manager (office_mgr)"


@pytest.mark.django_db
class TestMembershipRoleModel:

    def test_assign_role(self, member_with_role, role_manager):
        assert MembershipRole.objects.filter(
            membership=member_with_role, role=role_manager
        ).exists()

    def test_unique_constraint(self, member_with_role, role_manager):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            MembershipRole.objects.create(
                membership=member_with_role, role=role_manager
            )

    def test_multiple_roles(self, member_with_role, role_tech):
        MembershipRole.objects.create(membership=member_with_role, role=role_tech)
        assert member_with_role.membership_roles.count() == 2


# ──────────────────────────────────────────────
# Service: has_capability
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestHasCapability:

    def test_has_granted_capability(self, member_with_role):
        assert has_capability(member_with_role, "leads.view") is True
        assert has_capability(member_with_role, "leads.convert") is True
        assert has_capability(member_with_role, "pricing.preview") is True

    def test_missing_capability(self, member_with_role):
        assert has_capability(member_with_role, "quotes.approve") is False

    def test_no_roles_has_no_capabilities(self, member_no_roles):
        assert has_capability(member_no_roles, "leads.view") is False

    def test_none_membership(self):
        assert has_capability(None, "leads.view") is False

    def test_inactive_capability_not_granted(self, member_with_role, cap_inactive, role_manager):
        """Even if an inactive capability is assigned, it should not be granted."""
        RoleCapability.objects.create(role=role_manager, capability=cap_inactive)
        assert has_capability(member_with_role, "old.feature") is False

    def test_inactive_role_not_granted(self, member_with_role, role_manager):
        """Deactivating a role removes its capabilities."""
        role_manager.is_active = False
        role_manager.save()
        assert has_capability(member_with_role, "leads.view") is False

    def test_multi_role_union(self, member_with_role, role_tech, cap_leads_view):
        """Capabilities from multiple roles are unioned."""
        # role_tech only has leads.view, role_manager has leads.view + leads.convert + pricing.preview
        # Adding role_tech doesn't change anything but should still work
        MembershipRole.objects.create(membership=member_with_role, role=role_tech)
        assert has_capability(member_with_role, "leads.view") is True
        assert has_capability(member_with_role, "leads.convert") is True


# ──────────────────────────────────────────────
# Service: get_all_capabilities
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestGetAllCapabilities:

    def test_returns_all_codes(self, member_with_role):
        caps = get_all_capabilities(member_with_role)
        assert caps == {"leads.view", "leads.convert", "pricing.preview"}

    def test_empty_for_no_roles(self, member_no_roles):
        assert get_all_capabilities(member_no_roles) == set()

    def test_empty_for_none(self):
        assert get_all_capabilities(None) == set()

    def test_union_from_multiple_roles(self, member_with_role, role_tech):
        MembershipRole.objects.create(membership=member_with_role, role=role_tech)
        caps = get_all_capabilities(member_with_role)
        # leads.view appears in both roles but should only be in set once
        assert caps == {"leads.view", "leads.convert", "pricing.preview"}


# ──────────────────────────────────────────────
# Service: get_scope
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestGetScope:

    def test_default_scope_self_assigned(self, member_with_role):
        """No scope rules defined → defaults to SELF_ASSIGNED."""
        assert get_scope(member_with_role) == ScopeLevel.SELF_ASSIGNED

    def test_wildcard_scope(self, member_with_role, role_manager):
        ScopeRule.objects.create(
            role=role_manager, applies_to="*", scope_level=ScopeLevel.ALL_ORG
        )
        assert get_scope(member_with_role) == ScopeLevel.ALL_ORG

    def test_domain_specific_overrides_wildcard(self, member_with_role, role_manager):
        ScopeRule.objects.create(
            role=role_manager, applies_to="*", scope_level=ScopeLevel.ALL_ORG
        )
        ScopeRule.objects.create(
            role=role_manager, applies_to="leads", scope_level=ScopeLevel.SELF_ASSIGNED
        )
        # leads domain → SELF_ASSIGNED (specific overrides wildcard)
        assert get_scope(member_with_role, "leads") == ScopeLevel.SELF_ASSIGNED
        # other domains → ALL_ORG (wildcard)
        assert get_scope(member_with_role, "quotes") == ScopeLevel.ALL_ORG

    def test_broadest_scope_wins(self, member_with_role, role_manager, role_tech):
        """When multiple roles define scope, the broadest one wins."""
        MembershipRole.objects.create(membership=member_with_role, role=role_tech)
        ScopeRule.objects.create(
            role=role_manager, applies_to="*", scope_level=ScopeLevel.ALL_ORG
        )
        ScopeRule.objects.create(
            role=role_tech, applies_to="*", scope_level=ScopeLevel.SELF_ASSIGNED
        )
        assert get_scope(member_with_role) == ScopeLevel.ALL_ORG

    def test_none_membership(self):
        assert get_scope(None) == ScopeLevel.SELF_ASSIGNED


# ──────────────────────────────────────────────
# Service: require_capability decorator
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestRequireCapabilityDecorator:

    def test_allows_when_has_capability(self, member_with_role):
        @require_capability("leads.convert")
        def convert_lead(membership, lead_id):
            return f"converted-{lead_id}"

        result = convert_lead(member_with_role, 42)
        assert result == "converted-42"

    def test_raises_when_missing_capability(self, member_with_role):
        @require_capability("quotes.approve")
        def approve_quote(membership, quote_id):
            return "approved"

        with pytest.raises(PermissionDenied) as exc_info:
            approve_quote(member_with_role, 99)
        assert "quotes.approve" in str(exc_info.value)

    def test_raises_for_no_roles(self, member_no_roles):
        @require_capability("leads.view")
        def view_leads(membership):
            return "ok"

        with pytest.raises(PermissionDenied):
            view_leads(member_no_roles)

    def test_works_with_keyword_arg(self, member_with_role):
        @require_capability("leads.view")
        def view_leads(membership=None):
            return "ok"

        result = view_leads(membership=member_with_role)
        assert result == "ok"


# ──────────────────────────────────────────────
# Service: Role import from CSV
# ──────────────────────────────────────────────
@pytest.fixture
def seeded_caps(db):
    """Create a set of capabilities for import testing."""
    caps = {}
    for code in ["leads.view", "leads.convert", "pricing.preview", "quotes.view"]:
        caps[code] = Capability.objects.create(code=code, description=f"Test: {code}")
    return caps


@pytest.mark.django_db
class TestRoleImportDryRun:

    def test_dry_run_shows_creates(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += 'office_mgr,Office Manager,Manages office,false,"leads.view,leads.convert"\n'

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.created == ["office_mgr"]
        assert result.updated == []
        assert not result.has_errors
        # Verify nothing was actually created
        assert Role.objects.filter(organization=active_org).count() == 0

    def test_dry_run_shows_updates(self, active_org, seeded_caps):
        Role.objects.create(
            organization=active_org, code="office_mgr", name="Old Name"
        )
        csv = "code,name,description,is_system,capabilities\n"
        csv += 'office_mgr,New Name,Updated,false,"leads.view"\n'

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.updated == ["office_mgr"]
        # Verify name wasn't changed
        assert Role.objects.get(
            organization=active_org, code="office_mgr"
        ).name == "Old Name"

    def test_dry_run_shows_unchanged(self, active_org, seeded_caps):
        role = Role.objects.create(
            organization=active_org, code="office_mgr", name="Office Manager",
            description="Manages office"
        )
        role.capabilities.set([seeded_caps["leads.view"]])

        csv = "code,name,description,is_system,capabilities\n"
        csv += "office_mgr,Office Manager,Manages office,false,leads.view\n"

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.unchanged == ["office_mgr"]


@pytest.mark.django_db
class TestRoleImportCommit:

    def test_creates_role(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += 'office_mgr,Office Manager,Manages office,false,"leads.view,leads.convert"\n'

        result = import_roles_from_csv(active_org, csv, dry_run=False)

        assert result.created == ["office_mgr"]
        role = Role.objects.get(organization=active_org, code="office_mgr")
        assert role.name == "Office Manager"
        assert set(role.capabilities.values_list("code", flat=True)) == {
            "leads.view", "leads.convert"
        }

    def test_updates_existing_role(self, active_org, seeded_caps):
        Role.objects.create(
            organization=active_org, code="office_mgr", name="Old Name"
        )

        csv = "code,name,description,is_system,capabilities\n"
        csv += 'office_mgr,New Name,Updated desc,false,"pricing.preview"\n'

        result = import_roles_from_csv(active_org, csv, dry_run=False)

        role = Role.objects.get(organization=active_org, code="office_mgr")
        assert role.name == "New Name"
        assert role.description == "Updated desc"
        assert set(role.capabilities.values_list("code", flat=True)) == {"pricing.preview"}

    def test_idempotent_double_import(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += "office_mgr,Office Manager,Manages office,false,leads.view\n"

        result1 = import_roles_from_csv(active_org, csv, dry_run=False)
        result2 = import_roles_from_csv(active_org, csv, dry_run=False)

        assert result1.created == ["office_mgr"]
        assert result2.unchanged == ["office_mgr"]
        assert Role.objects.filter(organization=active_org, code="office_mgr").count() == 1

    def test_multiple_roles(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += "mgr,Manager,Manages,false,leads.view\n"
        csv += "tech,Technician,Field work,false,quotes.view\n"

        result = import_roles_from_csv(active_org, csv, dry_run=False)

        assert len(result.created) == 2
        assert Role.objects.filter(organization=active_org).count() == 2

    def test_empty_capabilities_allowed(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += "viewer,Viewer,View only,false,\n"

        result = import_roles_from_csv(active_org, csv, dry_run=False)

        assert result.created == ["viewer"]
        role = Role.objects.get(organization=active_org, code="viewer")
        assert role.capabilities.count() == 0

    def test_is_system_flag(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += "sysadmin,System Admin,Platform role,true,leads.view\n"

        import_roles_from_csv(active_org, csv, dry_run=False)

        role = Role.objects.get(organization=active_org, code="sysadmin")
        assert role.is_system is True


@pytest.mark.django_db
class TestRoleImportErrors:

    def test_unknown_capability(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += "mgr,Manager,Manages,false,leads.view\n"
        csv += "bad,Bad Role,Broken,false,nonexistent.cap\n"

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.has_errors
        assert any("nonexistent.cap" in e["error"] for e in result.errors)
        # Good row should NOT be in created (errors stop processing)
        assert result.created == []

    def test_duplicate_code_in_file(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += "mgr,Manager,Manages,false,leads.view\n"
        csv += "mgr,Manager Dupe,Duplicate,false,leads.view\n"

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.has_errors
        assert any("Duplicate" in e["error"] for e in result.errors)

    def test_missing_code(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += ",No Code,Missing code,false,leads.view\n"

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.has_errors
        assert any("Missing 'code'" in e["error"] for e in result.errors)

    def test_missing_name(self, active_org, seeded_caps):
        csv = "code,name,description,is_system,capabilities\n"
        csv += "mgr,,Missing name,false,leads.view\n"

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.has_errors
        assert any("Missing 'name'" in e["error"] for e in result.errors)

    def test_bad_header(self, active_org, seeded_caps):
        csv = "wrong,columns\n"
        csv += "a,b\n"

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.has_errors
        assert any("must have columns" in e["error"] for e in result.errors)

    def test_inactive_capability_rejected(self, active_org):
        Capability.objects.create(code="leads.view", description="View leads")
        Capability.objects.create(code="deprecated.thing", description="Old", is_active=False)

        csv = "code,name,description,is_system,capabilities\n"
        csv += "mgr,Manager,Manages,false,deprecated.thing\n"

        result = import_roles_from_csv(active_org, csv, dry_run=True)

        assert result.has_errors
        assert any("deprecated.thing" in e["error"] for e in result.errors)


# ──────────────────────────────────────────────
# Seed capabilities command
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestSeedCapabilities:

    def test_seed_creates_capabilities(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("seed_capabilities", stdout=out)

        assert Capability.objects.count() > 0
        assert Capability.objects.filter(code="leads.view").exists()
        assert Capability.objects.filter(code="leads.convert").exists()
        assert "created" in out.getvalue().lower()

    def test_seed_is_idempotent(self):
        from django.core.management import call_command
        from io import StringIO

        call_command("seed_capabilities", stdout=StringIO())
        count_after_first = Capability.objects.count()

        out = StringIO()
        call_command("seed_capabilities", stdout=out)
        count_after_second = Capability.objects.count()

        assert count_after_first == count_after_second
        assert "unchanged" in out.getvalue().lower()

    def test_seed_dry_run(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("seed_capabilities", "--dry-run", stdout=out)

        assert Capability.objects.count() == 0
        assert "DRY RUN" in out.getvalue()
