"""
apps.common.utils — Shared utilities for FlowLynk.
"""
import uuid


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for request tracing."""
    return uuid.uuid4().hex
