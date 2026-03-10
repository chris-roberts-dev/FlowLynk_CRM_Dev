"""
apps.platform.audit.models — Append-only audit event stream.

AuditEvent captures every significant action in the system with full
context: who did what, to which entity, with what inputs, and why.

This table is append-only. Records are never updated or deleted.
"""

from django.db import models


class EventCategory(models.TextChoices):
    """Broad categories for filtering audit events."""

    AUTH = "AUTH", "Authentication"
    DATA = "DATA", "Data change"
    IMPORT = "IMPORT", "Import operation"
    WORKFLOW = "WORKFLOW", "Workflow transition"
    OVERRIDE = "OVERRIDE", "Override / exception"
    SYSTEM = "SYSTEM", "System event"


class AuditEvent(models.Model):
    """
    Immutable audit record capturing a single action.

    Append-only — no update or delete operations should ever be
    performed on this table.

    org is nullable for global/platform-level events (e.g. user creation,
    platform config changes).
    """

    # ── Context ──────────────────────────────
    organization = models.ForeignKey(
        "platform_organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Owning organization. Null for global/platform events.",
    )
    actor_membership = models.ForeignKey(
        "platform_accounts.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Membership that performed the action. Null for system events.",
    )
    actor_email = models.EmailField(
        blank=True,
        default="",
        help_text="Denormalized actor email for readability when membership is deleted.",
    )

    # ── Event classification ─────────────────
    category = models.CharField(
        max_length=20,
        choices=EventCategory.choices,
        default=EventCategory.DATA,
        db_index=True,
    )
    event_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text=(
            "Specific event code, e.g. 'lead.created', 'quote.converted', "
            "'pricing.override', 'import.started'."
        ),
    )

    # ── Entity reference ─────────────────────
    entity_type = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Model name of the affected entity, e.g. 'Lead', 'Quote', 'Role'.",
    )
    entity_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Primary key of the affected entity.",
    )

    # ── Payload ──────────────────────────────
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured data: diff payload, inputs, outputs, context.",
    )
    reason = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Required for sensitive actions (overrides, reassignments, deletions). "
            "Free-text explanation of why the action was taken."
        ),
    )

    # ── Request context ──────────────────────
    correlation_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Request correlation ID for tracing.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP address from the request.",
    )
    user_agent = models.TextField(
        blank=True,
        default="",
        help_text="Client User-Agent header.",
    )

    # ── Timestamp ────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="idx_audit_org_created",
            ),
            models.Index(
                fields=["organization", "event_type"],
                name="idx_audit_org_event_type",
            ),
            models.Index(
                fields=["entity_type", "entity_id"],
                name="idx_audit_entity",
            ),
            models.Index(
                fields=["correlation_id"],
                name="idx_audit_correlation",
            ),
        ]
        # Prevent accidental updates/deletes at the application level.
        # The DB doesn't enforce this, but the convention is clear.
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"

    def __str__(self):
        actor = self.actor_email or "system"
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.event_type} by {actor}"

    def save(self, *args, **kwargs):
        """Only allow inserts, never updates."""
        if self.pk is not None:
            raise ValueError(
                "AuditEvent records are immutable. Cannot update an existing event."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of audit records."""
        raise ValueError(
            "AuditEvent records are immutable. Cannot delete an audit event."
        )
