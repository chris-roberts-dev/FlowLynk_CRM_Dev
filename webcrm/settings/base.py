"""
FlowLynk — Base settings.
Shared across dev / staging / prod. Environment-specific overrides
live in their own modules.

All environment variables are read via python-decouple so that:
- .env file is loaded automatically in dev
- os.environ is used in prod (Docker, systemd, etc.)
- Defaults are explicit and documented
"""

from pathlib import Path

from decouple import Csv, config

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
# BASE_DIR = <repo_root>/  (one level above webcrm/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ──────────────────────────────────────────────
# Application registry
# ──────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "django_extensions",
]

# Platform domain (global / non-tenant or tenant-adjacent)
PLATFORM_APPS = [
    "apps.platform.organizations",
    "apps.platform.accounts",
    "apps.platform.rbac",
    "apps.platform.audit",
    "apps.platform.billing",  # stub for now
]

# CRM domain (tenant-scoped)
CRM_APPS = [
    "apps.crm.locations",
    "apps.crm.catalog",
    "apps.crm.pricing",
    "apps.crm.leads",
    "apps.crm.quotes",
    "apps.crm.clients",
    "apps.crm.communications",
    "apps.crm.tasks",
    "apps.crm.reporting",
]

# Scheduling domain (tenant-scoped)
SCHEDULING_APPS = [
    "apps.scheduling.agreements",
    "apps.scheduling.visits",
    "apps.scheduling.assignments",
    "apps.scheduling.routing",
]

# Common / shared modules (only those that own DB tables)
COMMON_APPS = [
    "apps.common.importing",
]

INSTALLED_APPS = (
    DJANGO_APPS
    + THIRD_PARTY_APPS
    + PLATFORM_APPS
    + CRM_APPS
    + SCHEDULING_APPS
    + COMMON_APPS
)


# ──────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Tenant resolution: extracts subdomain, resolves Organization + Membership
    "apps.common.tenancy.middleware.TenantMiddleware",
    # Correlation ID: assigns unique request ID for tracing through logs + audit
    "apps.common.utils.middleware.CorrelationIdMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ──────────────────────────────────────────────
# URL config
# ──────────────────────────────────────────────
ROOT_URLCONF = "webcrm.urls"


# ──────────────────────────────────────────────
# Templates
# ──────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ──────────────────────────────────────────────
# WSGI / ASGI
# ──────────────────────────────────────────────
WSGI_APPLICATION = "webcrm.wsgi.application"
ASGI_APPLICATION = "webcrm.asgi.application"


# ──────────────────────────────────────────────
# Database — overridden per environment
# ──────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="flowlynk"),
        "USER": config("POSTGRES_USER", default="flowlynk"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="flowlynk"),
        "HOST": config("POSTGRES_HOST", default="localhost"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "OPTIONS": {
            "connect_timeout": 5,
        },
    }
}


# ──────────────────────────────────────────────
# Custom user model
# ──────────────────────────────────────────────
AUTH_USER_MODEL = "platform_accounts.User"


# ──────────────────────────────────────────────
# Password validation
# ──────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ──────────────────────────────────────────────
# Internationalization
# ──────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ──────────────────────────────────────────────
# Static files
# ──────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# ──────────────────────────────────────────────
# Default primary key type
# ──────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ──────────────────────────────────────────────
# FlowLynk — Platform settings
# ──────────────────────────────────────────────
# Base domain for public landing / login.  Subdomains resolve tenants.
PLATFORM_BASE_DOMAIN = config("PLATFORM_BASE_DOMAIN", default="lvh.me")
PLATFORM_PORT = config("PLATFORM_PORT", default="8000")

# ──────────────────────────────────────────────
# Sessions & Auth
# ──────────────────────────────────────────────
# Share session cookie across subdomains so login on base domain (lvh.me)
# carries over to tenant subdomains (acme.lvh.me).
# The leading dot is required for subdomain sharing.
SESSION_COOKIE_DOMAIN = config(
    "SESSION_COOKIE_DOMAIN",
    default=f".{PLATFORM_BASE_DOMAIN}",
)

# Where to redirect when @login_required triggers
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/auth/select-org/"
LOGOUT_REDIRECT_URL = "/"

# Logging — structured, ready for Sentry in prod
_LOG_LEVEL = config("LOG_LEVEL", default="DEBUG")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "context": {
            "()": "apps.common.utils.middleware.CorrelationIdFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
        "structured": {
            "format": (
                "[{asctime}] {levelname} {name} "
                "org={org_slug} actor={actor_id} cid={correlation_id} "
                "{message}"
            ),
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
            "filters": ["context"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": _LOG_LEVEL,
            "propagate": False,
        },
    },
}
