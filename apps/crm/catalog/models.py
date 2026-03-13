"""
apps.crm.catalog.models — Holistic catalog: Products, Services, and supporting entities.

Products: physical goods with inventory tracking, supplier links, BOM, reorder.
Services: recurring service offerings with duration, skills, recurrence, checklists.
Supporting: UnitOfMeasure, Supplier, ProductCategory, ServiceCategory, Material.

All models are tenant-scoped with code/sku uniqueness per organization.
"""

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.common.models.base import SoftDeleteModel, TenantModel

# =============================================================
# SUPPORTING ENTITIES
# =============================================================


# ─────────────────────────────────────────────────────────
# Unit of Measure
# ─────────────────────────────────────────────────────────
class UnitOfMeasure(TenantModel):
    """
    Defines how quantities are expressed (Each, Box, Gallon, Hour, etc.).
    Used by both Product and Service for pricing and inventory tracking.
    """

    name = models.CharField(
        max_length=50,
        help_text="Display name, e.g. Each, Box, Gallon, Hour.",
    )
    code = models.CharField(
        max_length=20,
        help_text="Short code, e.g. EA, BOX, GAL, HR.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_fractional = models.BooleanField(
        default=False,
        help_text="Whether this unit allows decimal quantities.",
    )
    precision = models.PositiveSmallIntegerField(
        default=0,
        help_text="Decimal places allowed when is_fractional=True.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="uq_uom_org_code"
            ),
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_uom_org_name"
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "is_active"], name="idx_uom_org_active"
            ),
        ]
        verbose_name = "Unit of Measure"
        verbose_name_plural = "Units of Measure"

    def __str__(self):
        return f"{self.code} — {self.name}"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()
        if self.name:
            self.name = self.name.strip()
        if not self.is_fractional and self.precision != 0:
            raise ValidationError(
                {"precision": "Precision must be 0 for non-fractional units."}
            )
        if self.is_fractional and self.precision <= 0:
            raise ValidationError(
                {"precision": "Precision must be > 0 for fractional units."}
            )


# ─────────────────────────────────────────────────────────
# Supplier
# ─────────────────────────────────────────────────────────
class Supplier(TenantModel):
    """
    Vendor / supplier master data for product purchasing.
    """

    name = models.CharField(max_length=255)
    code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Optional internal supplier code.",
    )
    contact_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    website = models.URLField(max_length=200, blank=True, default="")
    payment_terms = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="e.g. Net-30, Net-60, COD.",
    )
    account_number = models.CharField(max_length=100, blank=True, default="")

    # Address
    street = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=120, blank=True, default="")
    postal_code = models.CharField(max_length=30, blank=True, default="")
    country = models.CharField(max_length=120, blank=True, default="US")

    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_supplier_org_name"
            ),
            models.UniqueConstraint(
                fields=["organization", "code"],
                condition=~models.Q(code=""),
                name="uq_supplier_org_code_nonblank",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "is_active"], name="idx_supplier_org_active"
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
        if self.code:
            self.code = self.code.strip().upper()


# ─────────────────────────────────────────────────────────
# Product Category (hierarchical)
# ─────────────────────────────────────────────────────────
class ProductCategory(TenantModel):
    """
    Hierarchical product categorization for filtering and reporting.
    Supports parent/child nesting with cycle detection.
    """

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_prodcat_org_name"
            ),
            models.UniqueConstraint(
                fields=["organization", "slug"], name="uq_prodcat_org_slug"
            ),
        ]
        verbose_name = "Product Category"
        verbose_name_plural = "Product Categories"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.parent:
            if self.pk and self.parent_id == self.pk:
                raise ValidationError(
                    {"parent": "A category cannot be its own parent."}
                )
            # Skip cross-org check when organization hasn't been injected yet
            # (admin sets it in save_model after clean runs)
            if (
                self.organization_id
                and self.parent.organization_id != self.organization_id
            ):
                raise ValidationError(
                    {"parent": "Parent must belong to the same organization."}
                )
            # Cycle detection
            ancestor = self.parent
            seen = set()
            while ancestor is not None:
                if ancestor.pk in seen or (self.pk and ancestor.pk == self.pk):
                    raise ValidationError({"parent": "Circular nesting detected."})
                seen.add(ancestor.pk)
                ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────
# Service Category (hierarchical)
# ─────────────────────────────────────────────────────────
class ServiceCategory(TenantModel):
    """
    Hierarchical service categorization. Parallel to ProductCategory.
    Examples: Residential Cleaning, Commercial Cleaning, Specialty Services.
    """

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="uq_svccat_org_name"
            ),
            models.UniqueConstraint(
                fields=["organization", "slug"], name="uq_svccat_org_slug"
            ),
        ]
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.parent:
            if self.pk and self.parent_id == self.pk:
                raise ValidationError(
                    {"parent": "A category cannot be its own parent."}
                )
            if (
                self.organization_id
                and self.parent.organization_id != self.organization_id
            ):
                raise ValidationError(
                    {"parent": "Parent must belong to the same organization."}
                )
            ancestor = self.parent
            seen = set()
            while ancestor is not None:
                if ancestor.pk in seen or (self.pk and ancestor.pk == self.pk):
                    raise ValidationError({"parent": "Circular nesting detected."})
                seen.add(ancestor.pk)
                ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# =============================================================
# PRODUCT
# =============================================================


class Product(TenantModel, SoftDeleteModel):
    """
    Master record for a physical, sellable, or trackable item.

    Covers stock items, non-stock items, add-ons, and bundles.
    Supports inventory tracking, supplier linkage, BOM (components),
    and reorder management.
    """

    class ItemType(models.TextChoices):
        STOCK = "STOCK", "Stock"
        NON_STOCK = "NON_STOCK", "Non-Stock"
        ADD_ON = "ADD_ON", "Add-On"
        BUNDLE = "BUNDLE", "Bundle"

    class TrackingType(models.TextChoices):
        NONE = "NONE", "None"
        QUANTITY = "QUANTITY", "Quantity"
        SERIAL = "SERIAL", "Serial"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        ARCHIVED = "ARCHIVED", "Archived"

    class SourceType(models.TextChoices):
        PURCHASED = "PURCHASED", "Purchased"
        MANUFACTURED = "MANUFACTURED", "Manufactured"
        BOTH = "BOTH", "Purchased and Manufactured"

    # ── Scope: products are org-wide ─────────
    scope_field_region = None
    scope_field_market = None
    scope_field_location = None
    scope_field_assigned_to = None

    # ── Identity ─────────────────────────────
    name = models.CharField(max_length=255)
    sku = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Stock keeping unit, unique within the org. Auto-generated if blank.",
    )
    barcode = models.CharField(max_length=64, blank=True, default="")
    category = models.ForeignKey(
        ProductCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
        help_text="How this product is measured/priced.",
    )
    description = models.TextField(blank=True, default="")

    # ── Classification ───────────────────────
    item_type = models.CharField(
        max_length=20,
        choices=ItemType.choices,
        default=ItemType.STOCK,
        db_index=True,
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.PURCHASED,
    )
    tracking_type = models.CharField(
        max_length=20,
        choices=TrackingType.choices,
        default=TrackingType.NONE,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    # ── Flags ────────────────────────────────
    is_sellable = models.BooleanField(default=True)
    is_purchasable = models.BooleanField(default=True)
    is_consumable = models.BooleanField(
        default=False,
        help_text="Whether this product is consumed during service operations.",
    )

    # ── Pricing ──────────────────────────────
    default_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0000"),
        help_text="Internal cost per unit.",
    )
    default_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0000"),
        help_text="Default sell price per unit.",
    )

    # ── Reorder ──────────────────────────────
    reorder_enabled = models.BooleanField(default=False)
    reorder_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Reorder when stock falls below this level.",
    )
    reorder_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Suggested quantity to reorder.",
    )

    # ── Relationships ────────────────────────
    suppliers = models.ManyToManyField(
        "Supplier",
        through="ProductSupplierLink",
        related_name="products",
        blank=True,
    )
    bundle_items = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="in_bundles",
        help_text="Items included in this bundle (BUNDLE type only).",
    )

    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sku"],
                condition=~models.Q(sku=""),
                name="uq_product_org_sku_nonblank",
            ),
            models.UniqueConstraint(
                fields=["organization", "barcode"],
                condition=~models.Q(barcode=""),
                name="uq_product_org_barcode_nonblank",
            ),
            models.CheckConstraint(
                condition=models.Q(default_cost__gte=0),
                name="ck_product_cost_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(default_price__gte=0),
                name="ck_product_price_gte_0",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"], name="idx_product_org_status"
            ),
            models.Index(
                fields=["organization", "item_type"], name="idx_product_org_itemtype"
            ),
            models.Index(
                fields=["organization", "created_at"], name="idx_product_org_created"
            ),
        ]

    def __str__(self):
        label = self.sku or self.name
        return f"{label} — {self.name}" if self.sku else self.name

    def clean(self):
        super().clean()
        if self.sku:
            self.sku = self.sku.strip().upper()
        if self.barcode:
            self.barcode = self.barcode.strip()
        if (
            self.category
            and self.organization_id
            and self.category.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"category": "Category must belong to the same organization."}
            )
        if (
            self.tracking_type == self.TrackingType.SERIAL
            and self.item_type != self.ItemType.STOCK
        ):
            raise ValidationError(
                {"tracking_type": "Serial tracking is only for STOCK items."}
            )
        if self.reorder_enabled:
            if self.reorder_threshold is None:
                raise ValidationError(
                    {"reorder_threshold": "Required when reorder is enabled."}
                )
            if self.reorder_quantity is None:
                raise ValidationError(
                    {"reorder_quantity": "Required when reorder is enabled."}
                )
        else:
            self.reorder_threshold = None
            self.reorder_quantity = None

    def save(self, *args, **kwargs):
        if not self.sku:
            prefix = slugify(self.name)[:20].upper().replace("-", "")
            self.sku = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


# =============================================================
# SERVICE
# =============================================================


class RecurrenceType(models.TextChoices):
    ONE_TIME = "ONE_TIME", "One-time"
    WEEKLY = "WEEKLY", "Weekly"
    BIWEEKLY = "BIWEEKLY", "Biweekly"
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Quarterly"
    CUSTOM = "CUSTOM", "Custom"


class Service(TenantModel, SoftDeleteModel):
    """
    A recurring or one-time service offering.

    The core entity for scheduling, pricing, and quality workflows.
    Each service can have checklists, allowed add-ons, recurrence
    options, and skill requirements.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        ARCHIVED = "ARCHIVED", "Archived"

    # ── Scope: services are org-wide ─────────
    scope_field_region = None
    scope_field_market = None
    scope_field_location = None
    scope_field_assigned_to = None

    # ── Identity ─────────────────────────────
    code = models.CharField(
        max_length=50,
        help_text="Unique service code within the org, e.g. 'SVC-STD-CLEAN'.",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.ForeignKey(
        ServiceCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="services",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    # ── Operations ───────────────────────────
    base_duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Estimated time to complete (minutes).",
    )
    skill_tags = models.JSONField(
        default=list,
        blank=True,
        help_text='Skill tags for crew matching, e.g. ["carpet", "hardwood"].',
    )

    # ── Recurrence ───────────────────────────
    default_recurrence = models.CharField(
        max_length=20,
        choices=RecurrenceType.choices,
        default=RecurrenceType.ONE_TIME,
    )
    recurrence_options = models.JSONField(
        default=dict,
        blank=True,
        help_text='Allowed recurrence types with pricing multipliers: {"weekly": 1.0, "biweekly": 1.05}.',
    )

    # ── Pricing ──────────────────────────────
    base_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Base hourly or per-unit rate.",
    )
    base_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Flat base fee added to rate calculation.",
    )
    min_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Minimum charge regardless of calculation.",
    )
    travel_surcharge = models.BooleanField(
        default=False,
        help_text="Whether travel surcharge applies.",
    )
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="services",
        help_text="Pricing unit, e.g. per hour, per sqft.",
    )

    # ── Relationships ────────────────────────
    allowed_addons = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        related_name="addon_for_services",
        help_text="Other services that can be added on to this one.",
    )
    required_products = models.ManyToManyField(
        Product,
        blank=True,
        related_name="used_in_services",
        help_text="Products consumed or required when performing this service.",
    )

    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="uq_service_org_code"
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"], name="idx_service_org_status"
            ),
            models.Index(
                fields=["organization", "created_at"], name="idx_service_org_created"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def clean(self):
        super().clean()
        if self.code:
            self.code = self.code.strip().upper()
        if (
            self.category
            and self.organization_id
            and self.category.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"category": "Category must belong to the same organization."}
            )


# =============================================================
# PRODUCT RELATIONSHIPS
# =============================================================


# ─────────────────────────────────────────────────────────
# Product ↔ Supplier link
# ─────────────────────────────────────────────────────────
class ProductSupplierLink(TenantModel):
    """
    Join between Product and Supplier with purchasing details.
    Each product can have multiple suppliers; one can be marked preferred.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="supplier_links",
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="product_links",
    )
    supplier_sku = models.CharField(max_length=64, blank=True, default="")
    supplier_product_name = models.CharField(max_length=255, blank=True, default="")
    is_preferred = models.BooleanField(
        default=False,
        help_text="Preferred supplier for this product.",
    )
    last_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    lead_time_days = models.PositiveIntegerField(null=True, blank=True)
    minimum_order_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0000"),
    )

    class Meta:
        ordering = ["product__name", "supplier__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "product", "supplier"],
                name="uq_prodsuplink_org_prod_sup",
            ),
            models.UniqueConstraint(
                fields=["organization", "product"],
                condition=models.Q(is_preferred=True),
                name="uq_prodsuplink_one_preferred",
            ),
        ]
        verbose_name = "Product–Supplier Link"

    def __str__(self):
        return f"{self.product.name} ← {self.supplier.name}"

    def clean(self):
        super().clean()
        if (
            self.product
            and self.organization_id
            and self.product.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"product": "Product must belong to the same organization."}
            )
        if (
            self.supplier
            and self.organization_id
            and self.supplier.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"supplier": "Supplier must belong to the same organization."}
            )
        if self.product and self.product.source_type == Product.SourceType.MANUFACTURED:
            raise ValidationError(
                {
                    "product": "Manufactured products should not be linked to external suppliers."
                }
            )


# ─────────────────────────────────────────────────────────
# Product Component (BOM)
# ─────────────────────────────────────────────────────────
class ProductComponent(TenantModel):
    """
    Bill of Materials: defines what sub-products/materials make up
    a manufactured product.
    """

    parent_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="components",
    )
    component_product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="used_in_products",
    )
    quantity_required = models.DecimalField(max_digits=12, decimal_places=4)
    notes = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "parent_product", "component_product"],
                name="uq_prodcomp_org_parent_comp",
            ),
        ]
        verbose_name = "Product Component"

    def __str__(self):
        return f"{self.parent_product.name} ← {self.component_product.name} ×{self.quantity_required}"

    def clean(self):
        super().clean()
        if self.parent_product_id == self.component_product_id:
            raise ValidationError("A product cannot be a component of itself.")
        if (
            self.parent_product
            and self.organization_id
            and self.parent_product.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"parent_product": "Must belong to the same organization."}
            )
        if (
            self.component_product
            and self.organization_id
            and self.component_product.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"component_product": "Must belong to the same organization."}
            )


# ─────────────────────────────────────────────────────────
# Material (raw materials / internal supplies)
# ─────────────────────────────────────────────────────────
class Material(TenantModel):
    """
    Raw materials or internal supplies that are not sellable products
    but are consumed in operations or manufacturing.
    """

    class TrackingType(models.TextChoices):
        NONE = "NONE", "None"
        QUANTITY = "QUANTITY", "Quantity"
        SERIAL = "SERIAL", "Serial"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, help_text="Unique within the org.")
    barcode = models.CharField(max_length=64, blank=True, default="")
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="materials",
    )
    description = models.TextField(blank=True, default="")
    tracking_type = models.CharField(
        max_length=20,
        choices=TrackingType.choices,
        default=TrackingType.QUANTITY,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    is_purchasable = models.BooleanField(default=True)
    is_consumable = models.BooleanField(default=True)
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "sku"], name="uq_material_org_sku"
            ),
            models.UniqueConstraint(
                fields=["organization", "barcode"],
                condition=~models.Q(barcode=""),
                name="uq_material_org_barcode_nonblank",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"], name="idx_material_org_status"
            ),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}"

    def clean(self):
        super().clean()
        if self.sku:
            self.sku = self.sku.strip().upper()
        if self.barcode:
            self.barcode = self.barcode.strip()
        if self.unit_cost is not None and self.unit_cost < 0:
            raise ValidationError({"unit_cost": "Unit cost cannot be negative."})


# =============================================================
# CHECKLISTS (linked to Service)
# =============================================================


class ChecklistTemplate(TenantModel):
    """
    Quality checklist linked to a Service. Defines the steps crew
    must complete during a visit for this service.
    """

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="checklist_templates",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["service", "version"],
                name="uq_checklist_svc_version",
            ),
        ]
        ordering = ["service", "-version"]

    def __str__(self):
        return f"{self.name} v{self.version}"

    @property
    def item_count(self):
        return self.items.count()


class ChecklistItem(models.Model):
    """Individual step within a ChecklistTemplate."""

    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.CASCADE,
        related_name="items",
    )
    order = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=500)
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["template", "order"]

    def __str__(self):
        req = " *" if self.is_required else ""
        return f"{self.order}. {self.description}{req}"
