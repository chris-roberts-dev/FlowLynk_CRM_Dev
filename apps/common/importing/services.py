"""
apps.common.importing.services — Base import framework.

Provides BaseImporter that all app-specific importers extend.
Handles CSV parsing, dry-run/commit flow, row-level error collection,
ImportRun tracking, and audit event emission.

Usage:
    class LocationImporter(BaseImporter):
        import_type = ImportType.LOCATIONS
        required_columns = {"code", "name", "region_code", ...}

        def validate_row(self, line_num, row):
            ...  # return cleaned dict or call self.add_error()

        def apply_row(self, row_data):
            ...  # create/update DB records
"""

import csv
import io
import logging
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.common.importing.models import ImportRun, ImportStatus

logger = logging.getLogger(__name__)


class ImportResult:
    """Collects results from an import operation."""

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

    @property
    def row_count(self):
        return (
            len(self.created)
            + len(self.updated)
            + len(self.unchanged)
            + len(self.errors)
        )

    def add_error(self, line: int, code: str, error: str):
        self.errors.append({"line": line, "code": code, "error": error})


class BaseImporter:
    """
    Abstract base for all CSV importers.

    Subclasses must define:
        import_type: ImportType value
        required_columns: set of column names that must be in the CSV header

    Subclasses must implement:
        validate_row(line_num, row) → dict or None
            Parse and validate a single CSV row. Call self.result.add_error()
            on failure. Return a cleaned dict on success or None on error.

        apply_row(row_data) → str
            Apply a validated row to the database. Return one of
            'created', 'updated', or 'unchanged'.

    Subclasses may override:
        pre_validate(reader) → None
            Hook for global validation before row processing (e.g. loading
            valid parent codes).
    """

    import_type = None
    required_columns = set()

    def __init__(self, organization, membership=None):
        self.organization = organization
        self.membership = membership
        self.result = ImportResult()
        self._import_run = None

    def run(
        self, csv_content: str, dry_run: bool = True, file_name: str = ""
    ) -> ImportResult:
        """
        Execute the import.

        Args:
            csv_content: Raw CSV string content.
            dry_run: If True, validate only — no DB changes.
            file_name: Original filename for tracking.

        Returns:
            ImportResult with created/updated/unchanged/errors.
        """
        self.result = ImportResult()
        started_at = timezone.now()

        # Create ImportRun tracking record
        self._import_run = ImportRun.objects.create(
            organization=self.organization,
            actor_membership=(
                self.membership if self.membership and self.membership.pk else None
            ),
            import_type=self.import_type,
            file_name=file_name,
            is_dry_run=dry_run,
            status=ImportStatus.PENDING,
            started_at=started_at,
        )

        try:
            # Parse CSV
            reader = csv.DictReader(io.StringIO(csv_content))

            # Validate header
            if not self._validate_header(reader.fieldnames):
                self._finalize(ImportStatus.FAILED)
                return self.result

            # Pre-validation hook (load lookup tables, etc.)
            self.pre_validate(reader)

            # Collect and validate all rows
            validated_rows = []
            for line_num, row in enumerate(reader, start=2):  # line 1 = header
                row_data = self.validate_row(line_num, row)
                if row_data is not None:
                    validated_rows.append(row_data)

            # If validation errors exist, stop
            if self.result.has_errors:
                self._finalize(
                    ImportStatus.FAILED if not dry_run else ImportStatus.DRY_RUN
                )
                return self.result

            if dry_run:
                # Dry-run: simulate without DB changes
                for row_data in validated_rows:
                    action = self.classify_row(row_data)
                    getattr(self.result, action).append(
                        row_data.get("code", row_data.get("_label", ""))
                    )
                self._finalize(ImportStatus.DRY_RUN)
            else:
                # Commit: apply in a transaction
                with transaction.atomic():
                    for row_data in validated_rows:
                        action = self.apply_row(row_data)
                        label = row_data.get("code", row_data.get("_label", ""))
                        getattr(self.result, action).append(label)
                self._finalize(ImportStatus.COMMITTED)

            # Emit audit event
            self._emit_audit(dry_run)

        except Exception as e:
            logger.exception(
                "Import failed: %s for org '%s'",
                self.import_type,
                self.organization.slug,
            )
            self.result.add_error(0, "", f"Unexpected error: {e}")
            self._finalize(ImportStatus.FAILED)

        return self.result

    def _validate_header(self, fieldnames) -> bool:
        """Check that required columns exist in the CSV header."""
        if not fieldnames:
            self.result.add_error(0, "", "CSV file is empty or has no header row.")
            return False

        actual = set(fieldnames)
        missing = self.required_columns - actual
        if missing:
            self.result.add_error(
                0,
                "",
                f"Missing required columns: {', '.join(sorted(missing))}. "
                f"Found: {', '.join(sorted(actual))}",
            )
            return False
        return True

    def pre_validate(self, reader):
        """Override for global pre-validation (e.g. loading parent lookups)."""
        pass

    def validate_row(self, line_num: int, row: dict) -> dict | None:
        """Override: validate and clean a single row. Return dict or None."""
        raise NotImplementedError

    def classify_row(self, row_data: dict) -> str:
        """Override: return 'created', 'updated', or 'unchanged' for dry-run."""
        raise NotImplementedError

    def apply_row(self, row_data: dict) -> str:
        """Override: apply row to DB. Return 'created', 'updated', or 'unchanged'."""
        raise NotImplementedError

    def _finalize(self, status):
        """Update the ImportRun with final results."""
        if self._import_run:
            self._import_run.status = status
            self._import_run.completed_at = timezone.now()
            self._import_run.row_count = self.result.row_count
            self._import_run.created_count = len(self.result.created)
            self._import_run.updated_count = len(self.result.updated)
            self._import_run.unchanged_count = len(self.result.unchanged)
            self._import_run.error_count = len(self.result.errors)
            self._import_run.errors_json = self.result.errors
            self._import_run.save()

    def _emit_audit(self, dry_run: bool):
        """Emit an audit event for the import."""
        try:
            from apps.platform.audit.services import audit, EventCategory

            mode = "dry_run" if dry_run else "committed"
            audit.log(
                event_type=f"import.{mode}",
                category=EventCategory.IMPORT,
                membership=self.membership,
                organization=self.organization,
                entity_type="ImportRun",
                entity_id=str(self._import_run.pk) if self._import_run else "",
                metadata={
                    "import_type": self.import_type,
                    "file_name": self._import_run.file_name if self._import_run else "",
                    "summary": self.result.summary,
                },
            )
        except Exception:
            logger.warning("Failed to emit audit event for import", exc_info=True)
