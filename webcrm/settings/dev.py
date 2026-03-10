"""
FlowLynk — Development settings.

Usage:
    DJANGO_SETTINGS_MODULE=webcrm.settings.dev python manage.py runserver

Uses lvh.me which resolves to 127.0.0.1 and supports subdomains,
perfect for local tenant resolution testing.

All values read from .env via python-decouple (base.py handles DB,
platform domain, log level). This file only sets dev-specific overrides.
"""
from decouple import Csv, config

from .base import *  # noqa: F401,F403

# ──────────────────────────────────────────────
# Debug
# ──────────────────────────────────────────────
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)
SECRET_KEY = config(
    "DJANGO_SECRET_KEY",
    default="django-insecure-dev-only-change-in-production-flowlynk-2025",
)

# ──────────────────────────────────────────────
# Hosts
# Allow lvh.me and all subdomains for tenant resolution in dev.
# ──────────────────────────────────────────────
ALLOWED_HOSTS = config(
    "DJANGO_ALLOWED_HOSTS",
    default=".lvh.me,localhost,127.0.0.1",
    cast=Csv(),
)

# ──────────────────────────────────────────────
# Email — console backend for dev
# ──────────────────────────────────────────────
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

# ──────────────────────────────────────────────
# Logging — verbose in dev
# ──────────────────────────────────────────────
LOGGING["loggers"]["django.db.backends"] = {  # noqa: F405
    "handlers": ["console"],
    "level": "WARNING",  # Set to DEBUG to see SQL queries
    "propagate": False,
}
