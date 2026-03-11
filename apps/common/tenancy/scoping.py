"""
apps.common.tenancy.scoping — Scope-based visibility filtering.

Applies RBAC scope rules to querysets based on:
1. The membership's broadest scope level (from their roles)
2. The membership's geographic assignments (region, market, location)
3. The model's declared scope filter paths

How it works:
    - Each TenantModel declares scope_field_* attributes that map
      scope levels to queryset filter paths.
    - apply_scope() reads the membership's effective scope level,
      then filters the queryset accordingly.

Scope hierarchy (broadest → narrowest):
    ALL_ORG → no extra filter (sees everything in the org)
    REGION  → filter by membership.assigned_region
    MARKET  → filter by membership.assigned_market
    LOCATION → filter by membership.default_location
    SELF_ASSIGNED → filter by membership (assigned_to)

If a model doesn't declare a scope field for the resolved level,
the system falls through to the next narrower level. If no filter
path is found at all, it defaults to empty queryset (safe default).

Usage in admin:
    qs = apply_scope(qs, request.membership, Location)

Usage in services:
    qs = apply_scope(Lead.objects.all(), membership, Lead)
"""

import logging

from apps.platform.rbac.models import ScopeLevel
from apps.platform.rbac.services import get_scope

logger = logging.getLogger(__name__)

# Scope levels ordered from broadest to narrowest.
# Used for fallthrough when a model doesn't support a specific level.
_SCOPE_FALLTHROUGH = [
    ScopeLevel.ALL_ORG,
    ScopeLevel.REGION,
    ScopeLevel.MARKET,
    ScopeLevel.LOCATION,
    ScopeLevel.SELF_ASSIGNED,
]


def apply_scope(queryset, membership, model_class=None, domain="*"):
    """
    Filter a queryset based on the membership's effective scope.

    Args:
        queryset: The base queryset (already tenant-filtered by org).
        membership: The Membership to scope for. None = return empty.
        model_class: The model class (defaults to queryset.model).
                     Must declare scope_field_* attributes.
        domain: Scope domain for role lookup (default "*" = all).

    Returns:
        Filtered queryset.
    """
    if membership is None:
        return queryset.none()

    if model_class is None:
        model_class = queryset.model

    # Superuser stand-ins (unsaved membership) always get ALL_ORG
    if membership.pk is None:
        return queryset

    # Get effective scope level from RBAC
    scope_level = get_scope(membership, domain)

    # ALL_ORG = no additional filtering
    if scope_level == ScopeLevel.ALL_ORG:
        return queryset

    # Try the resolved scope level, then fall through to narrower levels
    start_index = _SCOPE_FALLTHROUGH.index(scope_level)

    for level in _SCOPE_FALLTHROUGH[start_index:]:
        if level == ScopeLevel.ALL_ORG:
            continue  # already handled above

        filter_kwargs = _build_filter(level, membership, model_class)
        if filter_kwargs is not None:
            logger.debug(
                "Scope filter applied: level=%s model=%s filter=%s member=%s",
                level,
                model_class.__name__,
                filter_kwargs,
                membership.pk,
            )
            return queryset.filter(**filter_kwargs)

    # No applicable scope filter found — safe default: show nothing
    logger.warning(
        "No scope filter path found for %s at level %s, returning empty queryset",
        model_class.__name__,
        scope_level,
    )
    return queryset.none()


def _build_filter(scope_level, membership, model_class):
    """
    Build a queryset filter dict for the given scope level.

    Returns dict of filter kwargs, or None if the model doesn't
    support this scope level.
    """
    if scope_level == ScopeLevel.REGION:
        field_path = getattr(model_class, "scope_field_region", None)
        value = membership.assigned_region_id
        if field_path and value:
            return {field_path: value}

    elif scope_level == ScopeLevel.MARKET:
        field_path = getattr(model_class, "scope_field_market", None)
        value = membership.assigned_market_id
        if field_path and value:
            return {field_path: value}

    elif scope_level == ScopeLevel.LOCATION:
        field_path = getattr(model_class, "scope_field_location", None)
        value = membership.default_location_id
        if field_path and value:
            return {field_path: value}

    elif scope_level == ScopeLevel.SELF_ASSIGNED:
        field_path = getattr(model_class, "scope_field_assigned_to", None)
        if field_path:
            return {field_path: membership}

    return None
