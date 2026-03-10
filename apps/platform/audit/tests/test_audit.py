"""
Tests for apps.platform.audit — EPIC 4 Audit Logging.

Validates:
- AuditEvent creation and immutability
- AuditService.log() with full context
- AuditService.log_from_request() request extraction
- Reason required for sensitive events
- Correlation ID injection
- Org-scoped queryset in admin
- Structured logging output
"""

import pytest
from django.test import RequestFactory

from apps.platform.audit.models import AuditEvent, EventCategory
from apps.platform.audit.services import AuditError, AuditService, audit
from apps.platform.organizations.models import OrganizationStatus


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────
@pytest.fixture
def active_org(make_organization):
    return make_organization(slug="acme", status=OrganizationStatus.ACTIVE)


@pytest.fixture
def member(make_user, active_org, make_membership):
    user = make_user(email="alice@acme.com")
    return make_membership(user=user, organization=active_org)


# ──────────────────────────────────────────────
# AuditEvent model
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestAuditEventModel:

    def test_create_event(self, active_org, member):
        event = AuditEvent.objects.create(
            organization=active_org,
            actor_membership=member,
            actor_email="alice@acme.com",
            event_type="lead.created",
            entity_type="Lead",
            entity_id="42",
            metadata={"source": "web"},
        )
        assert event.pk is not None
        assert event.created_at is not None
        assert event.category == EventCategory.DATA

    def test_immutable_no_update(self, active_org):
        event = AuditEvent.objects.create(
            organization=active_org,
            event_type="test.event",
        )
        with pytest.raises(ValueError, match="immutable"):
            event.event_type = "modified"
            event.save()

    def test_immutable_no_delete(self, active_org):
        event = AuditEvent.objects.create(
            organization=active_org,
            event_type="test.event",
        )
        with pytest.raises(ValueError, match="immutable"):
            event.delete()

    def test_str_representation(self, active_org):
        event = AuditEvent.objects.create(
            organization=active_org,
            actor_email="bob@acme.com",
            event_type="quote.sent",
        )
        result = str(event)
        assert "quote.sent" in result
        assert "bob@acme.com" in result

    def test_str_system_event(self, active_org):
        event = AuditEvent.objects.create(
            organization=active_org,
            event_type="import.started",
        )
        assert "system" in str(event)

    def test_nullable_org(self):
        """Global events can have null organization."""
        event = AuditEvent.objects.create(
            event_type="user.created",
            category=EventCategory.AUTH,
            actor_email="admin@flowlynk.com",
        )
        assert event.pk is not None
        assert event.organization is None

    def test_metadata_json(self, active_org):
        event = AuditEvent.objects.create(
            organization=active_org,
            event_type="lead.updated",
            metadata={
                "diff": {"status": {"old": "NEW", "new": "CONTACTED"}},
                "fields_changed": ["status"],
            },
        )
        event.refresh_from_db()
        assert event.metadata["diff"]["status"]["new"] == "CONTACTED"


# ──────────────────────────────────────────────
# AuditService.log()
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestAuditServiceLog:

    def test_log_creates_event(self, member, active_org):
        event = audit.log(
            event_type="lead.created",
            membership=member,
            entity_type="Lead",
            entity_id="99",
            metadata={"source": "phone"},
        )
        assert event.pk is not None
        assert event.event_type == "lead.created"
        assert event.organization == active_org
        assert event.actor_email == "alice@acme.com"
        assert event.entity_type == "Lead"
        assert event.entity_id == "99"
        assert event.metadata == {"source": "phone"}

    def test_log_derives_org_from_membership(self, member, active_org):
        event = audit.log(
            event_type="test.event",
            membership=member,
        )
        assert event.organization == active_org

    def test_log_explicit_org_overrides(self, member, make_organization):
        other_org = make_organization(slug="other", status=OrganizationStatus.ACTIVE)
        event = audit.log(
            event_type="test.event",
            membership=member,
            organization=other_org,
        )
        assert event.organization == other_org

    def test_log_without_membership(self, active_org):
        event = audit.log(
            event_type="import.started",
            category=EventCategory.IMPORT,
            organization=active_org,
        )
        assert event.actor_membership is None
        assert event.actor_email == ""

    def test_log_with_correlation_id(self, member):
        event = audit.log(
            event_type="test.event",
            membership=member,
            correlation_id="abc123",
        )
        assert event.correlation_id == "abc123"

    def test_log_with_ip_and_useragent(self, member):
        event = audit.log(
            event_type="test.event",
            membership=member,
            ip_address="192.168.1.1",
            user_agent="TestBrowser/1.0",
        )
        assert event.ip_address == "192.168.1.1"
        assert event.user_agent == "TestBrowser/1.0"

    def test_log_with_reason(self, member):
        event = audit.log(
            event_type="pricing.override",
            category=EventCategory.OVERRIDE,
            membership=member,
            reason="Loyalty discount approved by regional manager.",
        )
        assert event.reason == "Loyalty discount approved by regional manager."

    def test_log_sensitive_event_requires_reason(self, member):
        with pytest.raises(AuditError, match="requires a reason"):
            audit.log(
                event_type="pricing.override",
                membership=member,
                reason="",
            )

    def test_log_sensitive_event_whitespace_reason_rejected(self, member):
        with pytest.raises(AuditError, match="requires a reason"):
            audit.log(
                event_type="pricing.override",
                membership=member,
                reason="   ",
            )

    def test_log_non_sensitive_event_no_reason_ok(self, member):
        event = audit.log(
            event_type="lead.created",
            membership=member,
        )
        assert event.reason == ""

    def test_log_all_sensitive_events_enforced(self, member):
        """Every event in REASON_REQUIRED_EVENTS should fail without a reason."""
        from apps.platform.audit.services import REASON_REQUIRED_EVENTS

        for event_type in REASON_REQUIRED_EVENTS:
            with pytest.raises(AuditError):
                audit.log(event_type=event_type, membership=member, reason="")

    def test_log_global_event(self):
        event = audit.log(
            event_type="user.created",
            category=EventCategory.AUTH,
        )
        assert event.organization is None
        assert event.actor_membership is None


# ──────────────────────────────────────────────
# AuditService.log_from_request()
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestAuditServiceLogFromRequest:

    def _make_request(self, member, active_org, correlation_id="req-123"):
        factory = RequestFactory()
        request = factory.get(
            "/admin/",
            HTTP_HOST="acme.lvh.me:8000",
            HTTP_USER_AGENT="TestBrowser/2.0",
        )
        request.organization = active_org
        request.membership = member
        request.correlation_id = correlation_id
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        return request

    def test_extracts_all_context(self, member, active_org):
        request = self._make_request(member, active_org)

        event = audit.log_from_request(
            request,
            event_type="lead.viewed",
            entity_type="Lead",
            entity_id="55",
        )

        assert event.organization == active_org
        assert event.actor_email == "alice@acme.com"
        assert event.correlation_id == "req-123"
        assert event.ip_address == "10.0.0.1"
        assert event.user_agent == "TestBrowser/2.0"

    def test_extracts_forwarded_ip(self, member, active_org):
        factory = RequestFactory()
        request = factory.get(
            "/admin/",
            HTTP_HOST="acme.lvh.me:8000",
            HTTP_X_FORWARDED_FOR="203.0.113.50, 10.0.0.1",
        )
        request.organization = active_org
        request.membership = member
        request.correlation_id = "fwd-test"

        event = audit.log_from_request(request, event_type="test.event")

        # Should use first IP from X-Forwarded-For
        assert event.ip_address == "203.0.113.50"


# ──────────────────────────────────────────────
# Correlation ID middleware
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestCorrelationIdMiddleware:

    def test_generates_correlation_id(self):
        from django.test import Client

        client = Client()
        response = client.get("/", HTTP_HOST="lvh.me:8000")

        assert "X-Correlation-ID" in response
        assert len(response["X-Correlation-ID"]) == 32  # UUID hex

    def test_preserves_upstream_correlation_id(self):
        from django.test import Client

        client = Client()
        response = client.get(
            "/",
            HTTP_HOST="lvh.me:8000",
            HTTP_X_CORRELATION_ID="upstream-abc-123",
        )

        assert response["X-Correlation-ID"] == "upstream-abc-123"

    def test_correlation_id_on_request(self):
        from apps.common.utils.middleware import CorrelationIdMiddleware
        from django.http import HttpResponse

        def get_response(request):
            # Verify it's set during the request
            assert hasattr(request, "correlation_id")
            assert len(request.correlation_id) > 0
            return HttpResponse("OK")

        middleware = CorrelationIdMiddleware(get_response)
        factory = RequestFactory()
        request = factory.get("/", HTTP_HOST="lvh.me:8000")

        middleware(request)


# ──────────────────────────────────────────────
# Auto-injected correlation ID in audit events
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestAuditCorrelationIntegration:

    def test_audit_auto_picks_up_correlation_id(self, member):
        from apps.common.utils.middleware import _correlation_id

        # Simulate middleware setting the context var
        token = _correlation_id.set("test-correlation-xyz")
        try:
            event = audit.log(
                event_type="test.auto_cid",
                membership=member,
            )
            assert event.correlation_id == "test-correlation-xyz"
        finally:
            _correlation_id.set("")


# ──────────────────────────────────────────────
# Querying audit events
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestAuditQuerying:

    def test_filter_by_org(self, active_org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)

        AuditEvent.objects.create(organization=active_org, event_type="a.event")
        AuditEvent.objects.create(organization=active_org, event_type="b.event")
        AuditEvent.objects.create(organization=org_b, event_type="c.event")

        acme_events = AuditEvent.objects.filter(organization=active_org)
        assert acme_events.count() == 2

    def test_filter_by_event_type(self, active_org):
        AuditEvent.objects.create(organization=active_org, event_type="lead.created")
        AuditEvent.objects.create(organization=active_org, event_type="lead.created")
        AuditEvent.objects.create(organization=active_org, event_type="quote.sent")

        assert AuditEvent.objects.filter(event_type="lead.created").count() == 2

    def test_filter_by_entity(self, active_org):
        AuditEvent.objects.create(
            organization=active_org,
            event_type="lead.updated",
            entity_type="Lead",
            entity_id="42",
        )
        AuditEvent.objects.create(
            organization=active_org,
            event_type="lead.converted",
            entity_type="Lead",
            entity_id="42",
        )
        AuditEvent.objects.create(
            organization=active_org,
            event_type="lead.created",
            entity_type="Lead",
            entity_id="99",
        )

        # Get all events for Lead #42
        lead_42_events = AuditEvent.objects.filter(entity_type="Lead", entity_id="42")
        assert lead_42_events.count() == 2

    def test_filter_by_correlation_id(self, active_org):
        AuditEvent.objects.create(
            organization=active_org,
            event_type="a.event",
            correlation_id="req-aaa",
        )
        AuditEvent.objects.create(
            organization=active_org,
            event_type="b.event",
            correlation_id="req-aaa",
        )
        AuditEvent.objects.create(
            organization=active_org,
            event_type="c.event",
            correlation_id="req-bbb",
        )

        # Trace all events from one request
        assert AuditEvent.objects.filter(correlation_id="req-aaa").count() == 2

    def test_ordered_by_newest_first(self, active_org):
        e1 = AuditEvent.objects.create(organization=active_org, event_type="first")
        e2 = AuditEvent.objects.create(organization=active_org, event_type="second")

        events = list(AuditEvent.objects.all())
        assert events[0].pk == e2.pk  # newest first
