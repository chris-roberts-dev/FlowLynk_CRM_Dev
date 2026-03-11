"""
apps.platform.rbac.services — RBAC service layer.

Provides:
- has_capability(membership, code) → bool
- get_scope(membership, code_or_domain) → ScopeLevel
- require_capability decorator for service methods
- get_all_capabilities(membership) → set of codes
- Role import (CSV, dry-run, idempotent)
"""

import csv
import io
import logging
from functools import wraps

from django.db import transaction

from apps.platform.rbac.models import (
    Capability,
    MembershipRole,
    Role,
    RoleCapability,
    ScopeLevel,
    ScopeRule,
)

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    """Raised when a membership lacks the required capability."""

    def __init__(self, capability_code: str, membership=None):
        self.capability_code = capability_code
        self.membership = membership
        user_info = ""
        if membership:
            user_info = (
                f" (user={membership.user.email}, org={membership.organization.slug})"
            )
        super().__init__(
            f"Permission denied: missing capability '{capability_code}'{user_info}"
        )


# ──────────────────────────────────────────────
# Capability checks
# ──────────────────────────────────────────────
def get_all_capabilities(membership) -> set[str]:
    """
    Return the full set of active capability codes for a membership.

    This is the union of capabilities from all active roles assigned
    to the membership. Only active capabilities in active roles are included.
    """
    if membership is None:
        return set()

    return set(
        Capability.objects.filter(
            is_active=True,
            role_capabilities__role__is_active=True,
            role_capabilities__role__membership_roles__membership=membership,
        ).values_list("code", flat=True)
    )


def has_capability(membership, capability_code: str) -> bool:
    """
    Check if a membership has a specific capability.

    Returns True if any of the membership's active roles grant
    the given capability code (and the capability itself is active).
    """
    if membership is None:
        return False

    return Capability.objects.filter(
        code=capability_code,
        is_active=True,
        role_capabilities__role__is_active=True,
        role_capabilities__role__membership_roles__membership=membership,
    ).exists()


def get_scope(membership, domain: str = "*") -> ScopeLevel:
    """
    Get the effective scope level for a membership in a given domain.

    Resolution order:
    1. Look for a ScopeRule matching the exact domain on any of
       the membership's active roles.
    2. Fall back to wildcard domain ('*').
    3. Default to SELF_ASSIGNED if no rule exists.

    When multiple roles define scope for the same domain, the broadest
    scope wins (ALL_ORG > SELF_ASSIGNED).
    """
    if membership is None:
        return ScopeLevel.SELF_ASSIGNED

    # Get all scope rules from active roles assigned to this membership
    rules = ScopeRule.objects.filter(
        role__is_active=True,
        role__membership_roles__membership=membership,
    )

    # Check exact domain match first
    domain_rules = rules.filter(applies_to=domain)
    if domain_rules.exists():
        return _broadest_scope(domain_rules)

    # Fall back to wildcard
    wildcard_rules = rules.filter(applies_to="*")
    if wildcard_rules.exists():
        return _broadest_scope(wildcard_rules)

    return ScopeLevel.SELF_ASSIGNED


# Scope ordering: higher number = broader visibility
_SCOPE_ORDER = {
    ScopeLevel.SELF_ASSIGNED: 0,
    ScopeLevel.LOCATION: 10,
    ScopeLevel.MARKET: 20,
    ScopeLevel.REGION: 30,
    ScopeLevel.ALL_ORG: 40,
}


def _broadest_scope(rules_qs) -> ScopeLevel:
    """Given a queryset of ScopeRules, return the broadest scope level."""
    levels = list(rules_qs.values_list("scope_level", flat=True))
    return max(levels, key=lambda lvl: _SCOPE_ORDER.get(lvl, 0))


# ──────────────────────────────────────────────
# Decorator for service methods
# ──────────────────────────────────────────────
def require_capability(capability_code: str):
    """
    Decorator for service functions that require a capability.

    The decorated function must accept 'membership' as a keyword
    argument or as the first positional argument.

    Usage:
        @require_capability('leads.convert')
        def convert_lead(membership, lead_id):
            ...

    Raises PermissionDenied if the membership lacks the capability.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to extract membership from kwargs or first arg
            membership = kwargs.get("membership") or (args[0] if args else None)
            if not has_capability(membership, capability_code):
                raise PermissionDenied(capability_code, membership)
            return func(*args, **kwargs)

        return wrapper

    return decorator


# ──────────────────────────────────────────────
# Role import (CSV, dry-run, idempotent)
# ──────────────────────────────────────────────
class RoleImportResult:
    """Collects results from a role import operation."""

    def __init__(self):
        self.created = []
        self.updated = []
        self.unchanged = []
        self.errors = []

    @property
    def summary(self):
        return {
            "created": len(self.created),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged),
            "errors": len(self.errors),
        }

    @property
    def has_errors(self):
        return len(self.errors) > 0


def import_roles_from_csv(
    organization, csv_content: str, dry_run: bool = True
) -> RoleImportResult:
    """
    Import roles from CSV content.

    CSV format:
        code,name,description,is_system,capabilities
        office_manager,Office Manager,Manages office operations,false,"leads.view,leads.convert,quotes.view"
        field_tech,Field Tech,Field technician,false,"visits.view,quality.complete"

    - Idempotent by (organization, code): existing roles are updated.
    - capabilities column is a comma-separated list of capability codes.
    - Unknown capability codes are collected as errors.
    - If dry_run=True, no database changes are made.
    """
    result = RoleImportResult()
    reader = csv.DictReader(io.StringIO(csv_content))

    # Validate header
    required_fields = {"code", "name"}
    if not required_fields.issubset(set(reader.fieldnames or [])):
        result.errors.append(
            {
                "line": 0,
                "code": "",
                "error": f"CSV must have columns: {', '.join(sorted(required_fields))}. "
                f"Found: {', '.join(reader.fieldnames or [])}",
            }
        )
        return result

    # Pre-load active capabilities for validation
    valid_caps = set(
        Capability.objects.filter(is_active=True).values_list("code", flat=True)
    )

    rows = []
    seen_codes = set()

    for line_num, row in enumerate(reader, start=2):  # line 1 is header
        code = (row.get("code") or "").strip()
        name = (row.get("name") or "").strip()
        description = (row.get("description") or "").strip()
        is_system_str = (row.get("is_system") or "false").strip().lower()
        caps_str = (row.get("capabilities") or "").strip()

        # Validate required fields
        if not code:
            result.errors.append(
                {"line": line_num, "code": "", "error": "Missing 'code'"}
            )
            continue
        if not name:
            result.errors.append(
                {"line": line_num, "code": code, "error": "Missing 'name'"}
            )
            continue

        # Duplicate code check within the file
        if code in seen_codes:
            result.errors.append(
                {
                    "line": line_num,
                    "code": code,
                    "error": f"Duplicate code '{code}' in file",
                }
            )
            continue
        seen_codes.add(code)

        # Parse capabilities
        cap_codes = (
            [c.strip() for c in caps_str.split(",") if c.strip()] if caps_str else []
        )
        unknown_caps = [c for c in cap_codes if c not in valid_caps]
        if unknown_caps:
            result.errors.append(
                {
                    "line": line_num,
                    "code": code,
                    "error": f"Unknown capabilities: {', '.join(unknown_caps)}",
                }
            )
            continue

        is_system = is_system_str in ("true", "1", "yes")

        rows.append(
            {
                "line": line_num,
                "code": code,
                "name": name,
                "description": description,
                "is_system": is_system,
                "cap_codes": cap_codes,
            }
        )

    # If there are validation errors, stop before DB changes
    if result.has_errors:
        return result

    # Apply changes (skip if dry_run)
    if dry_run:
        # Simulate what would happen
        for row_data in rows:
            existing = Role.objects.filter(
                organization=organization, code=row_data["code"]
            ).first()
            if existing is None:
                result.created.append(row_data["code"])
            else:
                # Check if anything would change
                changed = (
                    existing.name != row_data["name"]
                    or existing.description != row_data["description"]
                    or existing.is_system != row_data["is_system"]
                    or set(existing.capabilities.values_list("code", flat=True))
                    != set(row_data["cap_codes"])
                )
                if changed:
                    result.updated.append(row_data["code"])
                else:
                    result.unchanged.append(row_data["code"])
        return result

    # Commit mode
    with transaction.atomic():
        cap_map = {c.code: c for c in Capability.objects.filter(is_active=True)}

        for row_data in rows:
            role, created = Role.objects.update_or_create(
                organization=organization,
                code=row_data["code"],
                defaults={
                    "name": row_data["name"],
                    "description": row_data["description"],
                    "is_system": row_data["is_system"],
                    "is_active": True,
                },
            )

            # Sync capabilities
            desired_caps = {cap_map[c] for c in row_data["cap_codes"] if c in cap_map}
            current_caps = set(role.capabilities.all())

            if created:
                result.created.append(row_data["code"])
            elif desired_caps != current_caps or role.name != row_data["name"]:
                result.updated.append(row_data["code"])
            else:
                result.unchanged.append(row_data["code"])

            # Replace capabilities (idempotent)
            role.capabilities.set(desired_caps)

    logger.info(
        "Role import completed for org '%s': %s",
        organization.slug,
        result.summary,
        extra={"org_id": organization.pk},
    )
    return result
