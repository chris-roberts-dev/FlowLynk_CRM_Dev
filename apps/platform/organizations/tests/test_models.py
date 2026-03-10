"""
Tests for apps.platform.organizations — EPIC 0 scaffold verification.

Validates:
- Organization model CRUD
- Status choices
- Slug uniqueness
"""
import pytest
from django.db import IntegrityError

from apps.platform.organizations.models import Organization, OrganizationStatus


@pytest.mark.django_db
class TestOrganizationModel:
    def test_create_organization(self, make_organization):
        org = make_organization(name="Acme Cleaning", slug="acme-cleaning")
        assert org.pk is not None
        assert org.name == "Acme Cleaning"
        assert org.slug == "acme-cleaning"
        assert org.status == OrganizationStatus.TRIAL
        assert org.created_at is not None

    def test_default_status_is_trial(self, make_organization):
        org = make_organization()
        assert org.status == OrganizationStatus.TRIAL

    def test_active_property(self, make_organization):
        org = make_organization(status=OrganizationStatus.ACTIVE)
        assert org.is_active is True
        assert org.is_suspended is False

    def test_suspended_property(self, make_organization):
        org = make_organization(status=OrganizationStatus.SUSPENDED)
        assert org.is_suspended is True
        assert org.is_active is False

    def test_slug_uniqueness(self, make_organization):
        make_organization(slug="unique-slug")
        with pytest.raises(IntegrityError):
            make_organization(slug="unique-slug")

    def test_str_representation(self, make_organization):
        org = make_organization(name="Demo Co", slug="demo-co")
        assert str(org) == "Demo Co (demo-co)"

    def test_settings_default_empty_dict(self, make_organization):
        org = make_organization()
        assert org.settings == {}
