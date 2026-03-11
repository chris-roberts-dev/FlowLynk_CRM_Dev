# FlowLynk

**Multi-Tenant SaaS CRM for Service & Sales Businesses**

FlowLynk is a CRM platform purpose-built for businesses that run recurring services — cleaning companies, landscaping franchises, pest control operations, and similar field service organizations. It treats route density, recurring schedules, and franchise oversight as first-class concerns rather than afterthoughts, giving operators a system that reduces day-to-day chaos while preserving the trust and consistency their customers expect.

The platform follows an admin-first development strategy: Django Admin serves as the primary interface for Phase 1, with a custom Bootstrap 5 tenant UI planned for Phase 2. This lets operators begin using the system immediately while the frontend matures in parallel.

---

## Table of Contents

- [Core Concepts](#core-concepts)
- [Architecture Overview](#architecture-overview)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration Reference](#configuration-reference)
- [Current Status](#current-status)
- [Development Roadmap](#development-roadmap)
- [Testing](#testing)
- [Design Decisions](#design-decisions)
- [Contributing](#contributing)
- [License](#license)

---

## Core Concepts

FlowLynk is organized around a small number of ideas that shape every part of the codebase.

**Multi-tenancy** is row-based. Every tenant-owned record carries an `organization_id` foreign key (or inherits one through a mandatory chain). There are no separate databases or schemas per tenant — isolation is enforced at the application layer through middleware, tenant-aware managers, and composite indexes. This keeps the operational footprint small while still guaranteeing that Org A never sees Org B's data.

**Tenant resolution** uses subdomains. In development, `acme.lvh.me:8000` resolves to the "acme" organization. In production, `acme.flowlynk.com` does the same. The base domain (`lvh.me` or `flowlynk.com`) serves the public landing page and login flow. Users with memberships in multiple organizations see an org picker after authentication.

**Service layer ownership** means that all business logic — mutations, transactions, row-level locking, RBAC enforcement, and audit event emission — lives in `services.py` files within each app. Models are kept thin. Admin actions and future API endpoints call services; they never perform business logic directly.

**RBAC** uses a two-axis model. The first axis is Capability: a global catalog of action codes like `leads.convert` or `pricing.preview` that are assigned to tenant-scoped Roles and granted to Memberships. The second axis is Scope: rules that control which records a member can see (ALL_ORG and SELF_ASSIGNED in Phase 1; REGION, MARKET, LOCATION, and TEAM planned for later). The admin interface is not considered a security boundary — RBAC is enforced in the service layer.

**Imports** are CSV-first (JSON optional for advanced use). Every import supports a dry-run preview that shows what would be created, updated, or rejected — with row-level error reporting and line numbers — before committing. Imports are idempotent: running the same file twice produces no duplicates. Every import run is recorded with an audit event.

**Audit logging** is append-only. Sensitive actions (pricing overrides, schedule changes, crew reassignments) require a reason. Every audit event captures the actor's membership, the affected entity, a diff payload, request metadata, and a correlation ID that threads through the entire request lifecycle.

---

## Architecture Overview

FlowLynk is a Django monolith organized into three domain groups, each containing focused Django apps. A fourth group (`common`) provides shared infrastructure that the other three depend on.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Django Admin (Phase 1 UI)                   │
│                     Custom AdminSite: Platform │ CRM                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  PLATFORM (global / tenant-adjacent)                                 │
│  ┌──────────────┬───────────┬────────┬─────────┬──────────┐         │
│  │organizations │ accounts  │  rbac  │  audit  │ billing  │         │
│  │  (tenant     │ (User,    │(Roles, │(append- │ (stub)   │         │
│  │   root)      │Membership)│ Caps)  │  only)  │          │         │
│  └──────────────┴───────────┴────────┴─────────┴──────────┘         │
│                                                                      │
│  CRM (tenant-scoped)                                                 │
│  ┌──────────┬─────────┬─────────┬───────┬────────┬─────────┐        │
│  │locations │ catalog │ pricing │ leads │ quotes │ clients │        │
│  ├──────────┴─────────┴─────────┴───────┴────────┴─────────┤        │
│  │  communications │  tasks  │  reporting                   │        │
│  └──────────────────┴─────────┴─────────────────────────────┘        │
│                                                                      │
│  SCHEDULING (tenant-scoped)                                          │
│  ┌────────────┬────────┬─────────────┬─────────┐                    │
│  │ agreements │ visits │ assignments │ routing │                    │
│  └────────────┴────────┴─────────────┴─────────┘                    │
│                                                                      │
│  COMMON (shared infrastructure — no business logic)                  │
│  ┌──────────┬────────┬───────┬───────────┬───────┬─────────┐        │
│  │ tenancy  │ models │ admin │ importing │ utils │ storage │        │
│  └──────────┴────────┴───────┴───────────┴───────┴─────────┘        │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                     PostgreSQL  (row-based multi-tenancy)             │
└──────────────────────────────────────────────────────────────────────┘
```

**Dependency rules** are strictly enforced:

- `common/*` must not import from `platform/*`, `crm/*`, or `scheduling/*`.
- `platform/*` may import `common/*`.
- `crm/*` may import `common/*` and `platform/*` (preferring stable interfaces).
- `scheduling/*` may import `common/*`; it avoids deep imports from `crm` apps and prefers IDs or service APIs for cross-domain communication.

**Admin grouping**: The Django Admin index displays exactly two top-level headings — **Platform** and **CRM** — implemented via a custom `AdminSite` that overrides `get_app_list()`. All `apps.platform.*` apps appear under Platform; everything else appears under CRM. Model-level permissions still control visibility.

---

## Technology Stack

| Layer         | Technology                                  |
|---------------|---------------------------------------------|
| Language      | Python 3.12+                                |
| Framework     | Django 5.1                                  |
| Database      | PostgreSQL 15+                              |
| DB Adapter    | psycopg 3 (binary)                          |
| Testing       | pytest, pytest-django, factory-boy          |
| Configuration | python-decouple (`.env` file support)       |
| Dev Tools     | django-extensions, IPython                  |
| Phase 1 UI    | Django Admin (custom AdminSite)             |
| Phase 2 UI    | Bootstrap 5 (planned)                       |
| Async Jobs    | Celery or RQ (planned for scheduling/reporting phases) |
| Monitoring    | Sentry (planned), structured logging        |

---

## Project Structure

```
flowlynk/
├── manage.py                          # Django management (defaults to dev settings)
├── requirements.txt                   # Python dependencies
├── pytest.ini                         # pytest configuration
├── conftest.py                        # Shared test fixtures (org, user, membership factories)
├── .env                               # Local environment variables (gitignored)
├── .env.example                       # Documented env var reference (committed)
├── .gitignore
│
├── webcrm/                            # Django project package
│   ├── settings/
│   │   ├── base.py                    # Shared settings (decouple-powered)
│   │   ├── dev.py                     # Development overrides (lvh.me, DEBUG=True)
│   │   └── prod.py                    # Production overrides (env-only secrets, TLS)
│   ├── urls.py                        # Root URL config (custom admin site)
│   ├── wsgi.py
│   └── asgi.py
│
├── apps/
│   ├── platform/                      # Global / tenant-adjacent domain
│   │   ├── organizations/             # Organization model (tenant root)
│   │   ├── accounts/                  # Custom User (email auth), Membership
│   │   ├── rbac/                      # Capability, Role, RoleCapability, ScopeRule
│   │   ├── audit/                     # AuditEvent append-only stream
│   │   └── billing/                   # Stub (reserved for future use)
│   │
│   ├── crm/                           # Tenant-scoped CRM domain
│   │   ├── locations/                 # Region → Market → Location hierarchy
│   │   ├── catalog/                   # Services, add-ons, bundles, checklists
│   │   ├── pricing/                   # Pricing versions, rules, snapshots
│   │   ├── leads/                     # Lead intake, qualification, conversion
│   │   ├── quotes/                    # Quote versions, line items, lifecycle
│   │   ├── clients/                   # Client records, service addresses
│   │   ├── communications/            # Inbound/outbound comms log
│   │   ├── tasks/                     # Unified work queue
│   │   └── reporting/                 # KPIs, aggregation
│   │
│   ├── scheduling/                    # Tenant-scoped operations domain
│   │   ├── agreements/                # Service plans / agreements
│   │   ├── visits/                    # Visit plans (templates) and instances
│   │   ├── assignments/               # Crew assignments per visit
│   │   └── routing/                   # Route boards, density metrics
│   │
│   └── common/                        # Shared infrastructure (no business logic)
│       ├── tenancy/                   # Middleware, tenant-aware managers
│       ├── models/                    # TimestampedModel, TenantModel, SoftDeleteModel
│       ├── admin/                     # FlowLynkAdminSite, TenantScopedAdmin
│       ├── importing/                 # Import framework (CSV/JSON, dry-run, ImportRun)
│       ├── utils/                     # Helpers (correlation IDs, etc.)
│       └── storage/                   # File storage backends (metadata-only Phase 1)
│
├── templates/
│   ├── admin/                         # Admin template overrides
│   └── platform/                      # Landing page, auth templates
│       └── landing.html               # Bootstrap 5 public landing stub
│
└── static/
    ├── css/
    └── js/
```

Every app follows a consistent internal layout:

```
app_name/
├── __init__.py
├── apps.py           # AppConfig with explicit label
├── models.py         # Data models (thin — no business logic)
├── admin.py          # Admin registration (calls services for actions)
├── services.py       # Service layer (transactions, RBAC, audit)
├── migrations/       # Django migrations
│   └── __init__.py
└── tests/            # App-specific tests
    └── __init__.py
```

Apps with import functionality additionally include `management/commands/` for CLI import commands.

---

## Getting Started

### Prerequisites

- Python 3.12 or later
- PostgreSQL 15 or later
- pip (or uv for faster installs)

### 1. Clone and enter the project

```bash
git clone <repository-url> flowlynk
cd flowlynk
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env if your Postgres credentials differ from the defaults
```

The default `.env` uses `flowlynk` / `flowlynk` / `flowlynk` for database name, user, and password. Adjust as needed.

### 5. Create the PostgreSQL database

```sql
CREATE USER flowlynk WITH PASSWORD 'flowlynk';
CREATE DATABASE flowlynk OWNER flowlynk;
ALTER USER flowlynk CREATEDB;  -- required for pytest to create test DB
```

### 6. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 7. Create a superuser

```bash
python manage.py createsuperuser
```

You will be prompted for an email and password (there is no username — email is the login identifier).

### 8. Start the development server

```bash
python manage.py runserver 0.0.0.0:8000
```

### 9. Access the application

- **Landing page**: [http://lvh.me:8000/](http://lvh.me:8000/)
- **Admin panel**: [http://lvh.me:8000/admin/](http://lvh.me:8000/admin/)
- **Tenant subdomain** (after creating an Organization with slug `acme`): [http://acme.lvh.me:8000/admin/](http://acme.lvh.me:8000/admin/)

`lvh.me` resolves to `127.0.0.1` and supports arbitrary subdomains, which makes it ideal for testing tenant resolution locally without modifying `/etc/hosts`.

### 10. Run the test suite

```bash
pytest
```

---

## Configuration Reference

All configuration is managed through environment variables, read via `python-decouple`. In development, values are loaded from the `.env` file in the project root. In production, values come from the process environment (Docker, systemd, etc.).

See `.env.example` for the full annotated reference. Key variables:

| Variable | Purpose | Dev Default | Prod Behavior |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | Which settings module to load | `webcrm.settings.dev` | `webcrm.settings.prod` |
| `DJANGO_SECRET_KEY` | Cryptographic signing key | Insecure dev placeholder | **Required — no default** (startup fails if missing) |
| `DJANGO_DEBUG` | Debug mode | `True` | Hardcoded `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames | `.lvh.me,localhost,127.0.0.1` | **Required — no default** |
| `POSTGRES_DB` | Database name | `flowlynk` | From environment |
| `POSTGRES_USER` | Database user | `flowlynk` | From environment |
| `POSTGRES_PASSWORD` | Database password | `flowlynk` | From environment |
| `POSTGRES_HOST` | Database host | `localhost` | From environment |
| `POSTGRES_PORT` | Database port | `5432` | From environment |
| `PLATFORM_BASE_DOMAIN` | Public base domain for tenancy | `lvh.me` | e.g., `flowlynk.com` |
| `PLATFORM_PORT` | Port appended to URLs | `8000` | Empty string (standard 443) |
| `EMAIL_BACKEND` | Django email backend class | Console (prints to stdout) | SMTP or transactional API |
| `LOG_LEVEL` | Log level for `apps.*` loggers | `DEBUG` | `INFO` |
| `SENTRY_DSN` | Sentry error tracking DSN | Empty (disabled) | Sentry project DSN |

Production settings intentionally have **no default** for `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`. A missing value raises `UndefinedValueError` at startup, preventing misconfigured deployments.

---

## Current Status

### EPIC 0 — Project Scaffold ✅ Complete

The project scaffold establishes the full directory structure, dependency configuration, settings pipeline, abstract base classes, custom admin infrastructure, and foundational models needed by every subsequent milestone.

**What was delivered:**

**Project infrastructure** — 19 Django apps across 4 domain groups, 174 Python files, three settings modules (`base.py`, `dev.py`, `prod.py`) powered by `python-decouple`, `.env` / `.env.example` with documented defaults for every configuration variable, `pytest.ini` with root `conftest.py` providing shared factory fixtures for Organization, User, and Membership, and `.gitignore` covering Python, Django, IDE, and environment files.

**Concrete models** (4 models ready for migration):

- **Organization** — tenant root with `name`, `slug` (unique, used for subdomain resolution), `status` (TRIAL / ACTIVE / SUSPENDED), and `settings` JSON field for tenant-level configuration.
- **User** — custom email-based authentication model (global, not tenant-scoped) built on `AbstractBaseUser` + `PermissionsMixin`, with status lifecycle (ACTIVE / LOCKED / INVITED).
- **Membership** — joins User to Organization with status tracking, unique constraint on (user, organization), multi-membership support, and optional default location FK.
- **Location** — stub with org-scoped code uniqueness, needed as a Membership FK target. Full hierarchy (Region → Market → Location) built in EPIC 5.

**Abstract base classes** (4 mixins for model inheritance):

- **TimestampedModel** — `created_at` (auto, indexed) and `updated_at` (auto).
- **AuditFieldsMixin** — `created_by` / `updated_by` FKs pointing to Membership.
- **SoftDeleteModel** — `is_deleted`, `deleted_at`, `deleted_by` for recoverable records.
- **TenantModel** — combines all three above plus `organization` FK. This is the standard base for every tenant-scoped model.

**Custom admin infrastructure**:

- **FlowLynkAdminSite** — overrides `get_app_list()` to group all apps under exactly two headings: **Platform** and **CRM**.
- **TenantScopedAdmin** — base `ModelAdmin` that auto-filters querysets by `request.organization`, auto-excludes tenant/audit fields from forms, and auto-injects `organization`, `created_by`, `updated_by` on save.
- Three admin registrations wired: Organization, User (with Membership inline), and Location.

**Tenancy infrastructure** (interface defined, full implementation in EPIC 1):

- **TenantMiddleware** — stub that sets `request.organization` and `request.membership`. Subdomain resolution logic is implemented in EPIC 1.
- **TenantManager / TenantQuerySet** — provide explicit `for_organization()` filtering. Automatic context-based filtering is added in EPIC 1.

**Test suite** — 24 tests across 3 modules:

- `test_models.py` (organizations) — 7 tests covering Organization CRUD, status properties, slug uniqueness, default settings JSON.
- `test_models.py` (accounts) — 13 tests covering User creation, superuser creation, email uniqueness and normalization, Membership creation, unique constraint enforcement, multi-membership across orgs, inactive membership.
- `test_admin_site.py` (common/admin) — 3 tests validating admin index shows only Platform and CRM groups, Organization appears under Platform, Location appears under CRM.

---

## Development Roadmap

The project is built iteratively in EPICs. Each EPIC is a self-contained milestone that delivers migrated models, admin wiring, service layer logic, and tests. EPICs are ordered by dependency — later EPICs build on earlier ones.

### Phase 1 — Platform Foundation

These EPICs establish the infrastructure that every subsequent feature depends on.

| EPIC | Name | Status | Description |
|------|------|--------|-------------|
| 0 | Project Scaffold | ✅ Complete | Directory structure, settings, base classes, foundational models, admin grouping, test fixtures |
| 1 | Tenancy Foundation | ✅ Complete | Subdomain-based tenant resolution middleware, auto-filtering querysets, landing page at base domain, invalid/suspended org handling, tenant isolation tests |
| 2 | Identity, Membership & Auth | ✅ Complete | Login flow (email → resolve membership → tenant redirect), org picker for multi-membership, logout to base domain, impersonation banner, session scoping |
| 3 | RBAC | ✅ Complete | Capability global catalog, Role (org-scoped), RoleCapability, MembershipRole, ScopeRule, RBACService with `has_capability` and `get_scope`, capability seeding migration, role import (CSV, dry-run, idempotent) |
| 4 | Audit Logging | ✅ Complete | AuditEvent model, AuditService, correlation ID middleware, structured JSON logging, read-only admin with filters |

### Phase 1 — Core CRM Pipeline

These EPICs build the lead → quote → client conversion pipeline that is central to the product.

| EPIC | Name | Status | Description |
|------|------|--------|-------------|
| 5 | Location Hierarchy & Import Framework | ✅ Complete | Common import framework (CSV parsing, dry-run, row-level errors, ImportRun tracking), Region → Market → Location models, location hierarchy importer, admin upload actions |
| 6 | Catalog & Checklist Templates | 🔲 Planned | CatalogItem (Service / Add-on / Product / Bundle), ChecklistTemplate, checklist items, catalog importer (CSV, idempotent) |
| 7 | Leads & Pricing Engine | 🔲 Planned | Lead model with full contact and service request fields, PricingVersion, PricingRule, PricingSnapshot, PricingService.preview(), admin "Preview Price" action that creates a snapshot without conversion |
| 8 | Quotes & Lead→Quote Conversion | 🔲 Planned | Quote model with versions, line items, and status lifecycle, atomic LeadService.convert_to_quote() with select_for_update and idempotency, admin "Convert Lead → Quote" action |
| 9 | Clients & Quote→Client Conversion | 🔲 Planned | Client, Contact, ServiceAddress, Agreement/ServicePlan, atomic QuoteService.accept() that creates all downstream records, soft-delete on Client and ServiceAddress |

### Phase 2 — Operational Extensions

These EPICs add task management, communications, and scheduling capabilities.

| EPIC | Name | Status | Description |
|------|------|--------|-------------|
| 10 | Tasks | 🔲 Planned | Task model (org-scoped, entity-linked, status lifecycle), TaskActivity (append-only), auto-creation triggers (lead → follow-up, quote → send, acceptance → onboarding), admin filters and inlines on Lead/Quote/Client |
| 11 | Communications | 🔲 Planned | CommunicationThread, Communication (direction, channel, status, body, entity linkage), CommunicationService (log-only in Phase 1, SMTP integration later), admin inlines and "Create Task from Communication" action |
| 12 | Scheduling & Routing | 🔲 Planned | VisitPlan with recurrence rules and consistency preferences, VisitInstance with status and checklist/issue links, Assignment model, RouteBoard per location/day with ordered sequence and density metrics, rolling horizon generation, exception queue (unassigned, over-capacity, long travel, late risk) |
| 13 | Quality & Trust | 🔲 Planned | ChecklistCompletion per visit, Issue model with type/severity/lifecycle, Rating per visit with optional NPS, rework workflow (open → triaged → scheduled → resolved), high-severity auto-triggers callback task |

### Phase 3 — Reporting & Hardening

| EPIC | Name | Status | Description |
|------|------|--------|-------------|
| 14 | Reporting & KPIs | 🔲 Planned | Indexed queries for sales metrics (lead volume, conversion rates, time-to-quote), ops metrics (utilization, on-time rate, rework rate), density metrics (drive time, visits/hour), trust metrics (rating trends, issue recurrence), task throughput and overdue rates, communications response times |
| 15 | Hardening & Production Readiness | 🔲 Planned | Host header validation, TLS enforcement, CSRF/session hardening, N+1 query audit across all admin views, prod settings finalization, Celery/RQ wiring for async jobs, Sentry integration, comprehensive tenant leak test suite covering ORM, admin, and service layers |

### Phase 4 — Custom Tenant UI (Future)

Phase 4 replaces the Django Admin with a Bootstrap 5 tenant-facing UI. This includes custom landing pages with optional tenant branding on subdomains, a login flow with email-based org discovery and org picker, dashboard views, and operator workflows designed for speed and mobile responsiveness. Phase 2 is not yet scoped in detail and will not begin until Phase 1 is complete and stable.

---

## Testing

Tests use `pytest` with `pytest-django`. The root `conftest.py` provides factory fixtures that are available to every test module without explicit imports.

### Running tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test module
pytest apps/platform/organizations/tests/test_models.py

# Run a specific test class
pytest apps/platform/accounts/tests/test_models.py::TestMembershipModel

# Run a specific test
pytest apps/platform/accounts/tests/test_models.py::TestUserModel::test_create_user

# Skip slow tests
pytest -m "not slow"
```

### Shared fixtures

The root `conftest.py` provides these fixtures:

| Fixture | Type | Description |
|---|---|---|
| `make_organization` | Factory | Creates an Organization with auto-incrementing slug. Accepts keyword overrides. |
| `make_user` | Factory | Creates a User with auto-incrementing email. Accepts keyword overrides. |
| `make_membership` | Factory | Creates a Membership linking a User to an Organization. Requires `user` and `organization` args. |
| `org` | Convenience | A single active Organization for simple tests. |
| `user` | Convenience | A single User for simple tests. |
| `membership` | Convenience | A single active Membership binding `user` to `org`. |

### Test categories

Tests are organized by what they validate. New categories are added with each EPIC:

- **Model tests** — CRUD operations, constraints, field defaults, computed properties, string representations.
- **Admin tests** — Admin site grouping, queryset filtering, permission visibility.
- **Tenancy tests** (starting EPIC 1) — Cross-tenant access attempts fail at ORM, admin, and service layers.
- **Workflow tests** (starting EPIC 7) — Lead → Quote conversion, pricing preview, quote acceptance, task auto-creation.
- **Import tests** (starting EPIC 5) — Dry-run correctness, idempotency, unknown code rejection, row-level error reporting.

### Current test coverage

24 tests across 3 modules:

- `apps/platform/organizations/tests/test_models.py` — 7 tests (Organization CRUD, status, slug uniqueness)
- `apps/platform/accounts/tests/test_models.py` — 13 tests (User auth, Membership constraints, multi-org)
- `apps/common/admin/tests/test_admin_site.py` — 3 tests (Platform/CRM grouping validation)

Test coverage grows with each EPIC. Tenancy isolation tests are a recurring requirement in every milestone.

---

## Design Decisions

This section documents key architectural choices and the reasoning behind them.

### Row-based multi-tenancy

Row-based tenancy with `organization_id` on every tenant-owned table was chosen because it keeps the operational model simple: one database, one connection pool, one migration path. This scales comfortably to hundreds of tenants. Schema-per-tenant adds migration complexity that is not justified at this stage. The tradeoff is that tenant isolation must be enforced at every application layer — middleware, managers, service methods, admin querysets, and tests — rather than relying on database-level separation.

### Email as the sole login identifier

Service businesses have operators, technicians, and franchise owners who often use personal email addresses. Requiring a separate username creates friction and forgotten-credential support burden. The custom User model uses `email` as `USERNAME_FIELD` and has no username field at all.

### Membership as the RBAC anchor

Audit trails and role grants are attached to Membership rather than User because the same person may have different roles in different organizations. A franchise owner might be an admin in Org A and a read-only viewer in Org B. Membership-level RBAC makes this natural without complex conditional logic.

### Service layer over fat models

Django's conventional approach puts business logic in model methods. FlowLynk instead uses explicit service modules (`services.py` per app) because multi-step workflows — like converting a lead to a quote while creating a pricing snapshot, emitting an audit event, and spawning a follow-up task — are clearer and safer when written as a single transactional service call. This also makes RBAC enforcement consistent: every entry point that mutates data goes through a service that checks capabilities.

### python-decouple over django-environ

`python-decouple` was chosen over `django-environ` because it has a smaller API surface, avoids database URL parsing magic that can obscure connection parameters, and provides clean separation between configuration declaration in settings files and value sourcing from `.env` or the process environment.

### Custom AdminSite with two-group index

Django's default admin groups models by app. With 19 apps, this creates a cluttered and disorienting index page. The custom `FlowLynkAdminSite` collapses everything into two headings (Platform and CRM) by inspecting each app's dotted name prefix. This matches how operators think about the system: "am I managing the platform, or am I managing my business?"

### Direct tenant FK as default

Most models carry `organization_id` directly (Pattern A) because it makes queries simple and indexes efficient. Chain-based scoping (Pattern B, e.g., QuoteLineItem → Quote → Organization) is allowed only when the child entity is tightly coupled to its parent and the FK chain is mandatory. Pattern B requires additional validation to prevent cross-org FK mismatch.

### Soft-delete for operational records

Clients, service addresses, catalog items, and visit plans use soft-delete (`is_deleted`, `deleted_at`, `deleted_by`) because these records may be referenced by historical quotes, invoices, or audit trails. Hard-deleting them would break referential integrity and lose audit context. Ephemeral records like draft task comments or import staging rows can be hard-deleted safely.

### CSV-first imports

The target users — franchise operators and office managers — work in spreadsheets. CSV is the format they can produce, inspect, and fix without developer help. JSON is supported as an optional format for automation and developer tooling, but CSV is the primary path and the one that receives dry-run preview UX in the admin.

### lvh.me for local development

`lvh.me` is a public DNS record that resolves `*.lvh.me` to `127.0.0.1`. This allows testing subdomain-based tenant resolution locally without editing `/etc/hosts`. The dev settings default to `PLATFORM_BASE_DOMAIN=lvh.me` and `PLATFORM_PORT=8000`, so `acme.lvh.me:8000` resolves correctly out of the box.

---

## Contributing

This project is under active development. When contributing:

1. Read the Technical Guide (`CRM_Technical_Guide.txt`) for full system requirements and specifications.
2. Follow the EPIC sequence — later EPICs depend on earlier ones being complete and stable.
3. Every app must have `apps.py`, `models.py`, `admin.py`, `services.py`, and a `tests/` directory.
4. Admin actions must delegate to services. Admin actions must never contain business logic directly.
5. All tenant-scoped models must inherit from `TenantModel` or at minimum carry an `organization` FK with `AuditFieldsMixin`.
6. Tests are required for tenancy isolation, RBAC enforcement, and critical workflows.
7. Imports must be idempotent with dry-run support and row-level error reporting.
8. Sensitive actions must emit audit events and require a reason where specified.
9. Prefer clarity and correctness over cleverness.

---

## License

Proprietary. All rights reserved.
