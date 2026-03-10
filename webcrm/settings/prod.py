"""
FlowLynk — Production settings.

All secrets sourced from environment variables (or .env if present).
Required vars with no default will raise UndefinedValueError on startup
if missing — this is intentional to prevent misconfigured deploys.
"""
from decouple import Csv, config

from .base import *  # noqa: F401,F403

# ──────────────────────────────────────────────
# Security
# ──────────────────────────────────────────────
DEBUG = False

# No default — forces explicit configuration in production.
SECRET_KEY = config("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", cast=Csv())

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ──────────────────────────────────────────────
# Database — read from base.py via decouple (POSTGRES_* vars).
# Override CONN_MAX_AGE for connection pooling in prod.
# ──────────────────────────────────────────────
DATABASES["default"]["CONN_MAX_AGE"] = config(  # noqa: F405
    "POSTGRES_CONN_MAX_AGE", default=600, cast=int
)

# ──────────────────────────────────────────────
# Static files — collected to STATIC_ROOT
# ──────────────────────────────────────────────
STATIC_ROOT = config("STATIC_ROOT", default="/var/www/flowlynk/static")

# ──────────────────────────────────────────────
# Email
# ──────────────────────────────────────────────
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

# ──────────────────────────────────────────────
# Platform
# ──────────────────────────────────────────────
PLATFORM_PORT = config("PLATFORM_PORT", default="")  # standard ports in prod (443)

# ──────────────────────────────────────────────
# Observability
# ──────────────────────────────────────────────
SENTRY_DSN = config("SENTRY_DSN", default="")

# Tighten log levels in production
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = config("LOG_LEVEL", default="INFO")  # noqa: F405
