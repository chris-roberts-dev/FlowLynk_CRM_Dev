"""
apps.crm.catalog.models — Service catalog: items, bundles, checklists.

CatalogItem: services, add-ons, products, and bundles.
ChecklistTemplate: quality steps tied to a service or bundle.
ChecklistItem: individual ordered steps within a template.

All models are tenant-scoped with code uniqueness per organization.
"""

from django.db import models

from apps.common.models.base import TenantModel


# ──────────────────────────────────────────────
# CatalogItem
# ──────────────────────────────────────────────
class ItemType(models.TextChoices):
    SERVICE = "SERVICE", "Service"
    ADD_ON = "ADD_ON", "Add-on"
    PRODUCT = "PRODUCT", "Product"
    BUNDLE = "BUNDLE", "Bundle"


class RecurrenceType(models.TextChoices):
    ONE_TIME = "ONE_TIME", "One-time"
    WEEKLY = "WEEKLY", "Weekly"
    BIWEEKLY = "BIWEEKLY", "Biweekly"
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Quarterly"


class CatalogItem(TenantModel):
    """
    A service, add-on, product, or bundle offered by the organization.

    Services are the core recurring offering (e.g. "Standard Cleaning").
    Add-ons are extras attached to services (e.g. "Interior Windows").
    Products are one-time physical goods (e.g. "Air Freshener Pack").
    Bundles group multiple services/add-ons together with pricing.

    Scope fields enable RBAC visibility filtering.
    """

    # ── Scope declarations ───────────────────
    # Catalog items are org-wide (no geographic scope).
    # All scope levels above SELF_ASSIGNED see everything.
    # Override in subclass if catalog becomes location-specific.
    scope_field_region = None
    scope_field_market = None
    scope_field_location = None
    scope_field_assigned_to = None

    # ── Identity ─────────────────────────────
    code = models.CharField(
        max_length=50,
        help_text="Unique code within the org, e.g. 'SVC-STD-CLEAN', 'AO-INT-WIN'.",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    item_type = models.CharField(
        max_length=20,
        choices=ItemType.choices,
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    # ── Operations ───────────────────────────
    base_duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Estimated time to complete this service (minutes). 0 for products.",
    )
    skill_tags = models.JSONField(
        default=list,
        blank=True,
        help_text='Skill tags for crew matching, e.g. ["carpet", "hardwood", "commercial"].',
    )

    # ── Recurrence ───────────────────────────
    default_recurrence = models.CharField(
        max_length=20,
        choices=RecurrenceType.choices,
        default=RecurrenceType.ONE_TIME,
        blank=True,
        help_text="Default recurrence for this service when creating visit plans.",
    )
    recurrence_options = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Allowed recurrence types with pricing factor multipliers. "
            'e.g. {"weekly": 1.0, "biweekly": 1.05, "monthly": 1.15}'
        ),
    )

    # ── Pricing inputs ───────────────────────
    base_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Base hourly or per-unit rate.",
    )
    base_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Flat base fee (added to rate-based calculation).",
    )
    min_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Minimum charge regardless of calculation.",
    )
    travel_surcharge = models.BooleanField(
        default=False,
        help_text="Whether travel surcharge applies to this item.",
    )

    # ── Relationships ────────────────────────
    allowed_addons = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="addon_for_items",
        limit_choices_to={"item_type": ItemType.ADD_ON},
        help_text="Add-on items that can be attached to this service/bundle.",
    )
    bundle_items = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="in_bundles",
        help_text="Items included in this bundle (only relevant for BUNDLE type).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uq_catalogitem_org_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "item_type"],
                name="idx_catalogitem_org_type",
            ),
            models.Index(
                fields=["organization", "is_active"],
                name="idx_catalogitem_org_active",
            ),
            models.Index(
                fields=["organization", "created_at"],
                name="idx_catalogitem_org_created",
            ),
        ]
        ordering = ["organization", "item_type", "name"]

    def __str__(self):
        return f"{self.name} ({self.code}) [{self.get_item_type_display()}]"

    @property
    def is_service(self):
        return self.item_type == ItemType.SERVICE

    @property
    def is_bundle(self):
        return self.item_type == ItemType.BUNDLE


# ──────────────────────────────────────────────
# ChecklistTemplate + ChecklistItem
# ──────────────────────────────────────────────
class ChecklistTemplate(TenantModel):
    """
    A quality checklist template linked to a catalog service or bundle.

    When a visit is performed for this service, the crew completes
    the checklist items. Templates are reusable across visits.
    """

    catalog_item = models.ForeignKey(
        CatalogItem,
        on_delete=models.CASCADE,
        related_name="checklist_templates",
        help_text="The service or bundle this checklist applies to.",
    )
    name = models.CharField(
        max_length=255,
        help_text="Template name, e.g. 'Standard Cleaning Checklist'.",
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(
        default=1,
        help_text="Version number. Increment when modifying an active template.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["catalog_item", "version"],
                name="uq_checklist_template_item_version",
            ),
        ]
        ordering = ["catalog_item", "-version"]

    def __str__(self):
        return f"{self.name} v{self.version}"

    @property
    def item_count(self):
        return self.items.count()


class ChecklistItem(models.Model):
    """
    A single step within a ChecklistTemplate.

    Ordered by 'order' field. Crew members check these off during visits.
    """

    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.CASCADE,
        related_name="items",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within the checklist.",
    )
    description = models.CharField(
        max_length=500,
        help_text="Step description, e.g. 'Vacuum all carpeted areas'.",
    )
    is_required = models.BooleanField(
        default=True,
        help_text="If true, this step must be completed for the checklist to pass.",
    )

    class Meta:
        ordering = ["template", "order"]

    def __str__(self):
        req = "*" if self.is_required else ""
        return f"{self.order}. {self.description}{req}"
