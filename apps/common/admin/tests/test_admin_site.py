"""
Tests for apps.common.admin.sites — Admin Platform/CRM grouping.

Validates:
- All apps appear under exactly two headings: Platform and CRM
- Platform apps grouped under Platform
- CRM/scheduling/common apps grouped under CRM
"""
import pytest
from django.test import RequestFactory

from apps.common.admin.sites import flowlynk_admin_site


@pytest.mark.django_db
class TestAdminSiteGrouping:
    def _get_app_list(self, user):
        """Helper: get admin app list for a given user."""
        factory = RequestFactory()
        request = factory.get("/admin/")
        request.user = user
        return flowlynk_admin_site.get_app_list(request)

    def test_only_two_groups(self, make_user):
        """Admin index must show at most Platform and CRM headings."""
        su = make_user(email="super@test.com")
        su.is_staff = True
        su.is_superuser = True
        su.save()

        app_list = self._get_app_list(su)
        group_names = [g["name"] for g in app_list]

        # Only Platform and CRM should appear (some may be empty if no models registered)
        for name in group_names:
            assert name in ("Platform", "CRM"), f"Unexpected group: {name}"

    def test_organization_in_platform_group(self, make_user):
        """Organization model should appear under Platform."""
        su = make_user(email="super2@test.com")
        su.is_staff = True
        su.is_superuser = True
        su.save()

        app_list = self._get_app_list(su)
        platform_group = next((g for g in app_list if g["name"] == "Platform"), None)
        assert platform_group is not None, "Platform group not found"

        model_names = [m["name"] for m in platform_group["models"]]
        assert "Organization" in model_names

    def test_location_in_crm_group(self, make_user):
        """Location model should appear under CRM."""
        su = make_user(email="super3@test.com")
        su.is_staff = True
        su.is_superuser = True
        su.save()

        app_list = self._get_app_list(su)
        crm_group = next((g for g in app_list if g["name"] == "CRM"), None)
        assert crm_group is not None, "CRM group not found"

        model_names = [m["name"] for m in crm_group["models"]]
        assert "Location" in model_names
