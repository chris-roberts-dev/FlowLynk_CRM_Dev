"""
apps.platform.audit.services — Audit logging service.

Provides AuditService.log() as the single entry point for recording
audit events from anywhere in the codebase. Service methods, admin
actions, and management commands all call this.

Usage:
    from apps.platform.audit.services import audit

    audit.log(
        membership=request.membership,
        event_type="lead.created",
        entity_type="Lead",
        entity_id=str(lead.pk),
        metadata={"source": "web_form", "fields": {...}},
    )

    # Sensitive action with required reason:
    audit.log(
        membership=request.membership,
        event_type="pricing.override",
        category=EventCategory.OVERRIDE,
        entity_type="PricingSnapshot",
        entity_id=str(snapshot.pk),
        metadata={"old_total": "500.00", "new_total": "350.00"},
        reason="Customer loyalty discount approved by regional manager.",
    )
"""

import logging

from apps.common.utils.middleware import get_correlation_id
from apps.platform.audit.models import AuditEvent, EventCategory

logger = logging.getLogger(__name__)

# Event types that require a reason. Add to this set as new
# sensitive actions are introduced.
REASON_REQUIRED_EVENTS = frozenset(
    {
        "pricing.override",
        "pricing.discount_applied",
        "schedule.override",
        "crew.reassigned",
        "refund.issued",
        "writeoff.created",
        "task.reassigned_protected",
        "communication.deleted",
        "communication.redacted",
        "member.deactivated",
        "role.system_modified",
    }
)


class AuditError(Exception):
    """Raised when an audit event cannot be recorded."""

    pass


class AuditService:
    """
    Centralized audit logging.

    All audit events flow through this service. It handles:
    - Reason validation for sensitive actions
    - Actor denormalization (email)
    - Correlation ID injection from request context
    - Structured logging alongside DB persistence
    """

    @staticmethod
    def log(
        event_type: str,
        membership=None,
        organization=None,
        category: str = EventCategory.DATA,
        entity_type: str = "",
        entity_id: str = "",
        metadata: dict | None = None,
        reason: str = "",
        ip_address: str | None = None,
        user_agent: str = "",
        correlation_id: str = "",
    ) -> AuditEvent:
        """
        Record an audit event.

        Args:
            event_type: Dotted event code (e.g. 'lead.created')
            membership: The Membership performing the action (None for system)
            organization: The Organization context (auto-derived from membership if not provided)
            category: EventCategory value
            entity_type: Model name of affected entity
            entity_id: PK of affected entity (as string)
            metadata: Arbitrary JSON-serializable context
            reason: Required for sensitive actions (see REASON_REQUIRED_EVENTS)
            ip_address: Client IP (pass from request if available)
            user_agent: Client User-Agent (pass from request if available)
            correlation_id: Override auto-detected correlation ID

        Returns:
            The created AuditEvent instance.

        Raises:
            AuditError: If reason is required but not provided.
        """
        # Validate reason for sensitive actions
        if event_type in REASON_REQUIRED_EVENTS and not reason.strip():
            raise AuditError(
                f"Audit event '{event_type}' requires a reason. "
                f"Sensitive actions must include an explanation."
            )

        # Derive organization from membership if not explicitly provided
        if organization is None and membership is not None:
            org = getattr(membership, "organization", None)
            # Handle unsaved superuser stand-in memberships
            if org is not None:
                organization = org

        # Denormalize actor email
        actor_email = ""
        if membership is not None:
            user = getattr(membership, "user", None)
            if user is not None:
                actor_email = user.email

        # Auto-detect correlation ID from request context
        if not correlation_id:
            correlation_id = get_correlation_id()

        event = AuditEvent.objects.create(
            organization=organization,
            actor_membership=membership if membership and membership.pk else None,
            actor_email=actor_email,
            category=category,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else "",
            metadata=metadata or {},
            reason=reason,
            correlation_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Also emit a structured log for real-time observability
        logger.info(
            "audit.%s entity=%s:%s actor=%s org=%s cid=%s",
            event_type,
            entity_type,
            entity_id,
            actor_email or "system",
            organization.slug if organization else "global",
            correlation_id,
            extra={
                "audit_event_id": event.pk,
                "event_type": event_type,
                "category": category,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "actor_email": actor_email,
                "org_id": organization.pk if organization else None,
                "correlation_id": correlation_id,
            },
        )

        return event

    @staticmethod
    def log_from_request(
        request,
        event_type: str,
        category: str = EventCategory.DATA,
        entity_type: str = "",
        entity_id: str = "",
        metadata: dict | None = None,
        reason: str = "",
    ) -> AuditEvent:
        """
        Convenience wrapper that extracts context from a Django request.

        Automatically pulls membership, organization, IP, user-agent,
        and correlation ID from the request object.
        """
        membership = getattr(request, "membership", None)
        organization = getattr(request, "organization", None)
        correlation_id = getattr(request, "correlation_id", "")

        # Extract client IP (handle proxied requests)
        ip_address = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        return AuditService.log(
            event_type=event_type,
            membership=membership,
            organization=organization,
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )


# Module-level convenience instance
audit = AuditService()
