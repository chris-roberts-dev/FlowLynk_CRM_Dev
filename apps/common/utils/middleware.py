"""
apps.common.utils.middleware — Request-level middleware utilities.

CorrelationIdMiddleware:
  Generates a unique correlation ID per request and stores it on:
  - request.correlation_id (for views/services to read)
  - Thread-local context var (for logging filter to inject into log records)
  - Response header X-Correlation-ID (for client tracing)
"""

import contextvars
import uuid

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    """Get the current request's correlation ID, or empty string."""
    return _correlation_id.get()


class CorrelationIdMiddleware:
    """
    Assigns a unique correlation ID to every request.

    If the incoming request has an X-Correlation-ID header (e.g. from
    a load balancer or upstream service), that value is used. Otherwise
    a new UUID is generated.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Use upstream correlation ID if provided, otherwise generate
        cid = request.META.get("HTTP_X_CORRELATION_ID", "") or uuid.uuid4().hex
        request.correlation_id = cid
        _correlation_id.set(cid)

        response = self.get_response(request)

        # Echo correlation ID in response header for client tracing
        response["X-Correlation-ID"] = cid

        # Clear context
        _correlation_id.set("")
        return response


class CorrelationIdFilter:
    """
    Logging filter that injects correlation_id, org_id, and actor_id
    into every log record.

    Usage in LOGGING config:
        "filters": {
            "context": {"()": "apps.common.utils.middleware.CorrelationIdFilter"},
        }
    """

    def filter(self, record):
        record.correlation_id = _correlation_id.get()

        # Try to get org_id and actor_id from tenancy context
        try:
            from apps.common.tenancy.context import (
                get_current_membership,
                get_current_organization,
            )

            org = get_current_organization()
            membership = get_current_membership()
            record.org_id = org.pk if org else ""
            record.org_slug = org.slug if org else ""
            record.actor_id = membership.pk if membership and membership.pk else ""
        except Exception:
            record.org_id = ""
            record.org_slug = ""
            record.actor_id = ""

        return True
