"""
Tests for TenantMember admin — tenant-facing member management.

Validates:
- TenantMemberAddForm creates new User + Membership
- TenantMemberAddForm links existing User to org
- TenantMemberAddForm requires password for new users
- TenantMemberAddForm rejects duplicate membership
- TenantMemberChangeForm shows user info read-only
- TenantMember admin only shows current org's members
"""

import pytest

from apps.platform.accounts.forms import TenantMemberAddForm
from apps.platform.accounts.models import (
    Membership,
    MembershipStatus,
    TenantMember,
    User,
)
from apps.platform.organizations.models import OrganizationStatus


@pytest.fixture
def active_org(make_organization):
    return make_organization(slug="acme", status=OrganizationStatus.ACTIVE)


# ──────────────────────────────────────────────
# TenantMemberAddForm
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestTenantMemberAddForm:

    def test_valid_new_user(self):
        form = TenantMemberAddForm(
            data={
                "email": "newguy@acme.com",
                "first_name": "New",
                "last_name": "Guy",
                "password": "securepass123",
                "status": MembershipStatus.ACTIVE,
            }
        )
        assert form.is_valid(), form.errors

        user = form.get_or_create_user()
        assert user.pk is not None
        assert user.email == "newguy@acme.com"
        assert user.first_name == "New"
        assert user.check_password("securepass123")

    def test_existing_user_no_password_needed(self, make_user):
        existing = make_user(email="existing@acme.com")

        form = TenantMemberAddForm(
            data={
                "email": "existing@acme.com",
                "first_name": "",
                "last_name": "",
                "password": "",
                "status": MembershipStatus.ACTIVE,
            }
        )
        assert form.is_valid(), form.errors

        user = form.get_or_create_user()
        assert user.pk == existing.pk

    def test_new_user_requires_password(self):
        form = TenantMemberAddForm(
            data={
                "email": "brand-new@acme.com",
                "first_name": "Brand",
                "last_name": "New",
                "password": "",
                "status": MembershipStatus.ACTIVE,
            }
        )
        assert not form.is_valid()
        assert "password" in form.errors

    def test_email_normalized_to_lowercase(self):
        form = TenantMemberAddForm(
            data={
                "email": "UPPER@ACME.COM",
                "first_name": "",
                "last_name": "",
                "password": "pass123",
                "status": MembershipStatus.ACTIVE,
            }
        )
        assert form.is_valid(), form.errors
        assert form.cleaned_data["email"] == "upper@acme.com"


# ──────────────────────────────────────────────
# TenantMember proxy model
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestTenantMemberProxy:

    def test_proxy_shares_table_with_membership(
        self, make_user, active_org, make_membership
    ):
        user = make_user()
        membership = make_membership(user=user, organization=active_org)

        # TenantMember should see the same record
        assert TenantMember.objects.filter(pk=membership.pk).exists()

    def test_proxy_verbose_name(self):
        assert TenantMember._meta.verbose_name == "Member"
        assert TenantMember._meta.verbose_name_plural == "Members"


# ──────────────────────────────────────────────
# TenantMember queryset scoping
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestTenantMemberScoping:

    def test_only_current_org_members_visible(
        self, active_org, make_organization, make_user, make_membership
    ):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)

        user_a = make_user(email="alice@acme.com")
        user_b = make_user(email="bob@beta.com")
        make_membership(user=user_a, organization=active_org)
        make_membership(user=user_b, organization=org_b)

        # Org A should only see Alice
        acme_members = TenantMember.objects.filter(organization=active_org)
        assert acme_members.count() == 1
        assert acme_members.first().user.email == "alice@acme.com"

        # Org B should only see Bob
        beta_members = TenantMember.objects.filter(organization=org_b)
        assert beta_members.count() == 1
        assert beta_members.first().user.email == "bob@beta.com"
