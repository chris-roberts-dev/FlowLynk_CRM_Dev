"""
apps.platform.rbac.models — Role-Based Access Control.

Two-axis authorization:
  1. Capability (what action can be performed)
  2. Scope (which records are visible)

Capability is a global catalog of stable action codes.
Role is an org-scoped bundle of capabilities.
MembershipRole assigns roles to memberships.
ScopeRule defines the visibility level for a role within an org.
"""

from django.db import models

from apps.common.models.base import TimestampedModel


# ──────────────────────────────────────────────
# Capability (global — not tenant-scoped)
# ──────────────────────────────────────────────
class Capability(TimestampedModel):
    """
    A single permission action in the system.

    Capabilities are global (not per-org). They are seeded via data
    migration and referenced by stable codes like 'leads.convert'.

    New capabilities are added as features ship. Existing codes
    must never be renamed or removed — only deactivated.
    """

    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Stable dotted code, e.g. 'leads.convert', 'pricing.preview'.",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Human-readable description of what this capability allows.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive capabilities are hidden from role assignment UI.",
    )

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "capabilities"

    def __str__(self):
        return self.code


# ──────────────────────────────────────────────
# Role (tenant-scoped)
# ──────────────────────────────────────────────
class Role(TimestampedModel):
    """
    A named bundle of capabilities within an organization.

    Examples: 'Office Manager', 'Field Tech', 'Franchise Owner'.
    System roles (is_system=True) cannot be deleted by org admins.
    """

    organization = models.ForeignKey(
        "platform_organizations.Organization",
        on_delete=models.CASCADE,
        related_name="roles",
    )
    code = models.CharField(
        max_length=100,
        help_text="Machine-readable code, unique within the org. Used for imports.",
    )
    name = models.CharField(
        max_length=255,
        help_text="Human-readable display name.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional longer description of this role's purpose.",
    )
    is_system = models.BooleanField(
        default=False,
        help_text="System roles are created by the platform and cannot be deleted by org admins.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )
    capabilities = models.ManyToManyField(
        Capability,
        through="RoleCapability",
        related_name="roles",
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uq_role_org_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "is_active"],
                name="idx_role_org_active",
            ),
        ]
        ordering = ["organization", "name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


# ──────────────────────────────────────────────
# RoleCapability (join table)
# ──────────────────────────────────────────────
class RoleCapability(models.Model):
    """Explicit join between Role and Capability."""

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="role_capabilities",
    )
    capability = models.ForeignKey(
        Capability,
        on_delete=models.CASCADE,
        related_name="role_capabilities",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "capability"],
                name="uq_role_capability",
            ),
        ]

    def __str__(self):
        return f"{self.role.code} → {self.capability.code}"


# ──────────────────────────────────────────────
# MembershipRole (assigns roles to memberships)
# ──────────────────────────────────────────────
class MembershipRole(TimestampedModel):
    """
    Assigns a Role to a Membership.

    A membership can have multiple roles. The effective capability
    set is the union of all assigned roles' capabilities.
    """

    membership = models.ForeignKey(
        "platform_accounts.Membership",
        on_delete=models.CASCADE,
        related_name="membership_roles",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="membership_roles",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "role"],
                name="uq_membership_role",
            ),
        ]

    def __str__(self):
        return f"{self.membership} ← {self.role.code}"


# ──────────────────────────────────────────────
# ScopeRule (visibility axis)
# ──────────────────────────────────────────────
class ScopeLevel(models.TextChoices):
    """
    Defines the breadth of records a role can see.

    Ordered broadest → narrowest:
        ALL_ORG > REGION > MARKET > LOCATION > SELF_ASSIGNED
    """

    ALL_ORG = "ALL_ORG", "All records in the organization"
    REGION = "REGION", "Records in assigned region"
    MARKET = "MARKET", "Records in assigned market"
    LOCATION = "LOCATION", "Records in assigned location"
    SELF_ASSIGNED = "SELF_ASSIGNED", "Only records assigned to user"


class ScopeRule(TimestampedModel):
    """
    Defines the visibility scope for a role.

    A role can have one ScopeRule per 'applies_to' domain. For example,
    a Field Tech role might have ALL_ORG scope for quality data but
    SELF_ASSIGNED scope for leads.

    Phase 1: single scope per role (applies_to='*' meaning all domains).
    """

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name="scope_rules",
    )
    applies_to = models.CharField(
        max_length=100,
        default="*",
        help_text=(
            "Domain this scope applies to. '*' = all domains. "
            "Future: 'leads', 'quotes', 'visits', etc."
        ),
    )
    scope_level = models.CharField(
        max_length=30,
        choices=ScopeLevel.choices,
        default=ScopeLevel.ALL_ORG,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["role", "applies_to"],
                name="uq_scope_rule_role_domain",
            ),
        ]
        ordering = ["role", "applies_to"]

    def __str__(self):
        return f"{self.role.code} [{self.applies_to}] → {self.scope_level}"
