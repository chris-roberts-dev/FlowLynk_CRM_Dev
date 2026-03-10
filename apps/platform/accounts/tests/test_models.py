"""
Tests for apps.platform.accounts — EPIC 0 scaffold verification.

Validates:
- User creation (email-based)
- Superuser creation
- Membership creation and uniqueness constraint
- Multi-membership support
"""
import pytest
from django.db import IntegrityError

from apps.platform.accounts.models import (
    Membership,
    MembershipStatus,
    User,
    UserStatus,
)


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self, make_user):
        user = make_user(email="alice@example.com")
        assert user.pk is not None
        assert user.email == "alice@example.com"
        assert user.check_password("testpass123")
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_create_superuser(self):
        su = User.objects.create_superuser(
            email="admin@flowlynk.com",
            password="superpass",
        )
        assert su.is_staff is True
        assert su.is_superuser is True

    def test_email_uniqueness(self, make_user):
        make_user(email="dup@example.com")
        with pytest.raises(IntegrityError):
            make_user(email="dup@example.com")

    def test_email_normalization(self, make_user):
        user = make_user(email="Bob@Example.COM")
        assert user.email == "Bob@example.com"

    def test_str_representation(self, make_user):
        user = make_user(email="test@test.com")
        assert str(user) == "test@test.com"

    def test_get_full_name(self, make_user):
        user = make_user(first_name="Alice", last_name="Smith")
        assert user.get_full_name() == "Alice Smith"

    def test_get_full_name_empty(self, make_user):
        user = make_user(email="no-name@test.com", first_name="", last_name="")
        assert user.get_full_name() == "no-name@test.com"

    def test_default_status(self, make_user):
        user = make_user()
        assert user.status == UserStatus.ACTIVE

    def test_create_user_without_email_raises(self):
        with pytest.raises(ValueError, match="Email is required"):
            User.objects.create_user(email="", password="test")


@pytest.mark.django_db
class TestMembershipModel:
    def test_create_membership(self, membership):
        assert membership.pk is not None
        assert membership.is_active is True

    def test_membership_str(self, membership):
        result = str(membership)
        assert "@" in result  # contains user email
        assert membership.organization.slug in result

    def test_unique_user_org_constraint(self, user, org, make_membership):
        make_membership(user=user, organization=org)
        with pytest.raises(IntegrityError):
            make_membership(user=user, organization=org)

    def test_multi_membership_different_orgs(
        self, user, make_organization, make_membership
    ):
        """A single user can belong to multiple organizations."""
        org_a = make_organization(slug="org-a")
        org_b = make_organization(slug="org-b")
        m1 = make_membership(user=user, organization=org_a)
        m2 = make_membership(user=user, organization=org_b)
        assert m1.pk != m2.pk
        assert user.memberships.count() == 2

    def test_inactive_membership(self, user, org, make_membership):
        m = make_membership(
            user=user,
            organization=org,
            status=MembershipStatus.INACTIVE,
        )
        assert m.is_active is False
