"""
Management command: seed_capabilities

Seeds the global Capability catalog. Idempotent — safe to run repeatedly.
New capabilities are added; existing ones are updated (description only).
No capabilities are ever deleted — only deactivated manually.

Usage:
    python manage.py seed_capabilities
    python manage.py seed_capabilities --dry-run
"""
from django.core.management.base import BaseCommand

from apps.platform.rbac.models import Capability

# ──────────────────────────────────────────────
# Capability catalog
# Add new capabilities here as features ship.
# NEVER remove or rename existing codes.
# ──────────────────────────────────────────────
CAPABILITIES = [
    # Locations
    ("locations.view", "View locations and hierarchy"),
    ("locations.manage", "Create, edit, and import locations"),

    # Catalog
    ("catalog.view", "View catalog items"),
    ("catalog.manage", "Create, edit, and import catalog items"),
    ("catalog.import", "Import catalog via CSV"),

    # Leads
    ("leads.view", "View leads"),
    ("leads.manage", "Create and edit leads"),
    ("leads.convert", "Convert a lead to a quote"),
    ("leads.assign", "Assign leads to team members"),
    ("leads.delete", "Delete leads"),

    # Pricing
    ("pricing.view", "View pricing versions and rules"),
    ("pricing.manage", "Create and edit pricing rules"),
    ("pricing.preview", "Generate pricing previews / snapshots"),

    # Quotes
    ("quotes.view", "View quotes"),
    ("quotes.manage", "Create and edit quotes"),
    ("quotes.send", "Send quotes to prospects"),
    ("quotes.approve", "Approve quotes above threshold"),
    ("quotes.accept", "Accept a quote and convert to client"),

    # Clients
    ("clients.view", "View client records"),
    ("clients.manage", "Create and edit client records"),

    # Tasks
    ("tasks.view", "View tasks"),
    ("tasks.manage", "Create and edit tasks"),
    ("tasks.assign", "Assign tasks to team members"),
    ("tasks.complete", "Mark tasks as complete"),

    # Communications
    ("communications.view", "View communications"),
    ("communications.send", "Send / log communications"),
    ("communications.manage", "Manage communication records"),

    # Scheduling
    ("scheduling.view", "View schedules and visit plans"),
    ("scheduling.manage", "Create and edit visit plans"),
    ("scheduling.assign", "Assign crew to visits"),

    # Routing
    ("routing.view", "View route boards"),
    ("routing.manage", "Manage route boards and sequences"),

    # Quality
    ("quality.view", "View quality data, checklists, ratings"),
    ("quality.manage", "Manage issues and rework"),
    ("quality.complete", "Complete checklists on visits"),

    # Audit
    ("audit.view", "View audit trail"),

    # Reporting
    ("reporting.view", "View reports and KPIs"),
    ("reporting.export", "Export report data"),

    # Admin / org management
    ("org.manage", "Manage organization settings"),
    ("roles.manage", "Manage roles and capability grants"),
    ("members.manage", "Manage memberships and role assignments"),
    ("imports.manage", "Run imports (locations, catalog, roles)"),
]


class Command(BaseCommand):
    help = "Seed the global Capability catalog. Idempotent."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created/updated without making changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created_count = 0
        updated_count = 0
        unchanged_count = 0

        for code, description in CAPABILITIES:
            try:
                cap = Capability.objects.get(code=code)
                if cap.description != description:
                    if not dry_run:
                        cap.description = description
                        cap.save(update_fields=["description", "updated_at"])
                    updated_count += 1
                    self.stdout.write(f"  UPDATE: {code}")
                else:
                    unchanged_count += 1
                    if options.get("verbosity", 1) > 1:
                        self.stdout.write(f"  UNCHANGED: {code}")
            except Capability.DoesNotExist:
                if not dry_run:
                    Capability.objects.create(code=code, description=description)
                created_count += 1
                self.stdout.write(f"  CREATE: {code}")

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Capabilities: "
                f"{created_count} created, "
                f"{updated_count} updated, "
                f"{unchanged_count} unchanged. "
                f"Total in catalog: {len(CAPABILITIES)}"
            )
        )
