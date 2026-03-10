"""
Tests for apps.platform.organizations.views — LandingPageView.

Validates:
- Landing page renders at /
- Error codes from query params display appropriate messages
- Unknown error codes are silently ignored
"""
import pytest
from django.test import Client


@pytest.mark.django_db
class TestLandingPageView:

    def test_landing_page_renders(self):
        client = Client()
        response = client.get("/", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        assert b"FlowLynk" in response.content

    def test_invalid_org_error(self):
        client = Client()
        response = client.get("/?error=invalid_org", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        assert b"could not be found" in response.content

    def test_org_suspended_error(self):
        client = Client()
        response = client.get("/?error=org_suspended", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        assert b"suspended" in response.content

    def test_no_membership_error(self):
        client = Client()
        response = client.get("/?error=no_membership", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        assert b"do not have access" in response.content

    def test_login_required_error(self):
        client = Client()
        response = client.get("/?error=login_required", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        assert b"Please log in" in response.content

    def test_unknown_error_code_ignored(self):
        client = Client()
        response = client.get("/?error=xss_attempt", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        # No error alert div should appear for unknown codes
        assert b'role="alert"' not in response.content

    def test_no_error_param_shows_clean_page(self):
        client = Client()
        response = client.get("/", HTTP_HOST="lvh.me:8000")
        assert response.status_code == 200
        assert b'role="alert"' not in response.content
