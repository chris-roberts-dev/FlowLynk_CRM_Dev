"""
Management command: import_locations

Import location hierarchy (Region → Market → Location) from CSV.

Usage:
    python manage.py import_locations acme locations.csv
    python manage.py import_locations acme locations.csv --commit
"""

from django.core.management.base import BaseCommand, CommandError

from apps.platform.organizations.models import Organization
from apps.crm.locations.services import LocationImporter


class Command(BaseCommand):
    help = "Import location hierarchy from CSV. Default is dry-run."

    def add_arguments(self, parser):
        parser.add_argument("org_slug", help="Organization slug.")
        parser.add_argument("csv_file", help="Path to the CSV file.")
        parser.add_argument(
            "--commit",
            action="store_true",
            help="Apply changes. Without this flag, runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        org_slug = options["org_slug"]
        csv_path = options["csv_file"]
        dry_run = not options["commit"]

        try:
            org = Organization.objects.get(slug=org_slug)
        except Organization.DoesNotExist:
            raise CommandError(f"Organization '{org_slug}' not found.")

        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                csv_content = f.read()
        except FileNotFoundError:
            raise CommandError(f"File not found: {csv_path}")

        mode = "DRY RUN" if dry_run else "COMMIT"
        self.stdout.write(f"\n[{mode}] Importing locations into '{org.name}'...\n")

        importer = LocationImporter(organization=org)
        result = importer.run(csv_content, dry_run=dry_run, file_name=csv_path)

        if result.errors:
            self.stdout.write(self.style.ERROR("\nErrors:"))
            for err in result.errors:
                self.stdout.write(
                    f"  Line {err['line']}: [{err['code']}] {err['error']}"
                )

        if result.created:
            self.stdout.write(self.style.SUCCESS(f"\nCreated ({len(result.created)}):"))
            for code in result.created:
                self.stdout.write(f"  + {code}")

        if result.updated:
            self.stdout.write(self.style.WARNING(f"\nUpdated ({len(result.updated)}):"))
            for code in result.updated:
                self.stdout.write(f"  ~ {code}")

        if result.unchanged:
            self.stdout.write(f"\nUnchanged ({len(result.unchanged)})")

        self.stdout.write(f"\nSummary: {result.summary}")

        if dry_run and not result.has_errors:
            self.stdout.write(self.style.NOTICE("\nDry run. Use --commit to apply."))
