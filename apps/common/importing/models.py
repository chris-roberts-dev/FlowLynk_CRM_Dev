"""
apps.common.importing.models — Import run tracking.

ImportRun records every import attempt (dry-run or commit) with
full result details: row counts, errors, timing, and the actor.
"""

from django.db import models

from apps.common.models.base import TimestampedModel


class ImportType(models.TextChoices):
    LOCATIONS = "LOCATIONS", "Location Hierarchy"
    CATALOG = "CATALOG", "Catalog Items"
    ROLES = "ROLES", "Roles"
    OTHER = "OTHER", "Other"


class ImportStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DRY_RUN = "DRY_RUN", "Dry Run Complete"
    COMMITTED = "COMMITTED", "Committed"
    FAILED = "FAILED", "Failed"


class ImportRun(TimestampedModel):
    """
    Records a single import attempt with full result tracking.

    Every import (dry-run or commit) creates an ImportRun. This provides
    a complete audit trail of what was imported, by whom, and what happened.
    """

    organization = models.ForeignKey(
        "platform_organizations.Organization",
        on_delete=models.CASCADE,
        related_name="import_runs",
    )
    actor_membership = models.ForeignKey(
        "platform_accounts.Membership",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    import_type = models.CharField(
        max_length=30,
        choices=ImportType.choices,
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    status = models.CharField(
        max_length=20,
        choices=ImportStatus.choices,
        default=ImportStatus.PENDING,
        db_index=True,
    )
    is_dry_run = models.BooleanField(default=True)

    # Result counts
    row_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    # Detailed errors (line-level)
    errors_json = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {line, code, error} dicts.",
    )

    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "import_type", "created_at"],
                name="idx_importrun_org_type_date",
            ),
        ]

    def __str__(self):
        mode = "dry-run" if self.is_dry_run else "commit"
        return (
            f"{self.get_import_type_display()} ({mode}) — "
            f"{self.status} — {self.file_name or 'unnamed'}"
        )
