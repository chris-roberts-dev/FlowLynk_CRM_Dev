"""
apps.crm.catalog.services — Product and Service importers.

ProductImporter CSV format:
    sku,name,item_type,category,description,source_type,tracking_type,
    is_sellable,is_purchasable,is_consumable,default_cost,default_price

ServiceImporter CSV format:
    code,name,category,description,base_duration_minutes,skill_tags,
    default_recurrence,recurrence_options,base_rate,base_fee,min_charge,
    travel_surcharge
"""

import uuid
import logging
from decimal import Decimal, InvalidOperation

from django.utils.text import slugify

from apps.common.importing.models import ImportType
from apps.common.importing.services import BaseImporter
from apps.crm.catalog.models import (
    Product,
    ProductCategory,
    Service,
    ServiceCategory,
)

logger = logging.getLogger(__name__)


# =============================================================
# Product Importer
# =============================================================

VALID_ITEM_TYPES = {t.value for t in Product.ItemType}
VALID_SOURCE_TYPES = {t.value for t in Product.SourceType}
VALID_TRACKING_TYPES = {t.value for t in Product.TrackingType}


class ProductImporter(BaseImporter):
    import_type = ImportType.CATALOG
    required_columns = {"name", "item_type"}

    def __init__(self, organization, membership=None):
        super().__init__(organization, membership)
        self._existing = {}
        self._seen_skus = {}
        self._categories = {}

    def pre_validate(self, reader):
        self._existing = {
            p.sku: p
            for p in Product.unscoped_objects.filter(organization=self.organization)
            if p.sku
        }
        self._categories = {
            c.name.lower(): c
            for c in ProductCategory.unscoped_objects.filter(
                organization=self.organization, is_active=True
            )
        }

    def validate_row(self, line_num, row):
        name = (row.get("name") or "").strip()
        sku = (row.get("sku") or "").strip().upper()
        item_type = (row.get("item_type") or "STOCK").strip().upper()

        if not name:
            self.result.add_error(line_num, sku, "Missing 'name'")
            return None

        if item_type not in VALID_ITEM_TYPES:
            self.result.add_error(line_num, sku, f"Invalid item_type '{item_type}'")
            return None

        # Generate SKU if blank
        if not sku:
            prefix = slugify(name)[:20].upper().replace("-", "")
            sku = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        # Duplicate SKU in file
        if sku in self._seen_skus:
            self.result.add_error(
                line_num, sku, f"Duplicate SKU (first on line {self._seen_skus[sku]})"
            )
            return None
        self._seen_skus[sku] = line_num

        # Category lookup (optional)
        category_name = (row.get("category") or "").strip()
        category = (
            self._categories.get(category_name.lower()) if category_name else None
        )

        source_type = (row.get("source_type") or "PURCHASED").strip().upper()
        if source_type not in VALID_SOURCE_TYPES:
            source_type = "PURCHASED"

        tracking_type = (row.get("tracking_type") or "NONE").strip().upper()
        if tracking_type not in VALID_TRACKING_TYPES:
            tracking_type = "NONE"

        return {
            "_label": sku,
            "sku": sku,
            "name": name,
            "item_type": item_type,
            "description": (row.get("description") or "").strip(),
            "category": category,
            "source_type": source_type,
            "tracking_type": tracking_type,
            "is_sellable": _parse_bool(row.get("is_sellable"), True),
            "is_purchasable": _parse_bool(row.get("is_purchasable"), True),
            "is_consumable": _parse_bool(row.get("is_consumable"), False),
            "default_cost": _parse_decimal(row.get("default_cost")),
            "default_price": _parse_decimal(row.get("default_price")),
        }

    def classify_row(self, row_data):
        existing = self._existing.get(row_data["sku"])
        if existing is None:
            return "created"
        changed = (
            existing.name != row_data["name"]
            or existing.item_type != row_data["item_type"]
            or existing.default_price != row_data["default_price"]
            or existing.default_cost != row_data["default_cost"]
        )
        return "updated" if changed else "unchanged"

    def apply_row(self, row_data):
        product, created = Product.unscoped_objects.update_or_create(
            organization=self.organization,
            sku=row_data["sku"],
            defaults={
                "name": row_data["name"],
                "item_type": row_data["item_type"],
                "description": row_data["description"],
                "category": row_data["category"],
                "source_type": row_data["source_type"],
                "tracking_type": row_data["tracking_type"],
                "is_sellable": row_data["is_sellable"],
                "is_purchasable": row_data["is_purchasable"],
                "is_consumable": row_data["is_consumable"],
                "default_cost": row_data["default_cost"],
                "default_price": row_data["default_price"],
                "status": Product.Status.ACTIVE,
            },
        )
        self._existing[row_data["sku"]] = product
        return "created" if created else "updated"


# =============================================================
# Service Importer
# =============================================================


class ServiceImporter(BaseImporter):
    import_type = ImportType.CATALOG
    required_columns = {"code", "name"}

    def __init__(self, organization, membership=None):
        super().__init__(organization, membership)
        self._existing = {}
        self._seen_codes = {}
        self._categories = {}

    def pre_validate(self, reader):
        self._existing = {
            s.code: s
            for s in Service.unscoped_objects.filter(organization=self.organization)
        }
        self._categories = {
            c.name.lower(): c
            for c in ServiceCategory.unscoped_objects.filter(
                organization=self.organization, is_active=True
            )
        }

    def validate_row(self, line_num, row):
        code = (row.get("code") or "").strip().upper()
        name = (row.get("name") or "").strip()

        if not code:
            self.result.add_error(line_num, "", "Missing 'code'")
            return None
        if not name:
            self.result.add_error(line_num, code, "Missing 'name'")
            return None

        if code in self._seen_codes:
            self.result.add_error(
                line_num,
                code,
                f"Duplicate code (first on line {self._seen_codes[code]})",
            )
            return None
        self._seen_codes[code] = line_num

        category_name = (row.get("category") or "").strip()
        category = (
            self._categories.get(category_name.lower()) if category_name else None
        )

        return {
            "_label": code,
            "code": code,
            "name": name,
            "description": (row.get("description") or "").strip(),
            "category": category,
            "base_duration_minutes": _parse_int(row.get("base_duration_minutes")),
            "skill_tags": _parse_semicolon_list(row.get("skill_tags")),
            "default_recurrence": (row.get("default_recurrence") or "ONE_TIME")
            .strip()
            .upper(),
            "recurrence_options": _parse_recurrence_options(
                row.get("recurrence_options")
            ),
            "base_rate": _parse_decimal(row.get("base_rate")),
            "base_fee": _parse_decimal(row.get("base_fee")),
            "min_charge": _parse_decimal(row.get("min_charge")),
            "travel_surcharge": _parse_bool(row.get("travel_surcharge"), False),
        }

    def classify_row(self, row_data):
        existing = self._existing.get(row_data["code"])
        if existing is None:
            return "created"
        changed = (
            existing.name != row_data["name"]
            or existing.base_rate != row_data["base_rate"]
            or existing.base_fee != row_data["base_fee"]
            or existing.base_duration_minutes != row_data["base_duration_minutes"]
        )
        return "updated" if changed else "unchanged"

    def apply_row(self, row_data):
        service, created = Service.unscoped_objects.update_or_create(
            organization=self.organization,
            code=row_data["code"],
            defaults={
                "name": row_data["name"],
                "description": row_data["description"],
                "category": row_data["category"],
                "base_duration_minutes": row_data["base_duration_minutes"],
                "skill_tags": row_data["skill_tags"],
                "default_recurrence": row_data["default_recurrence"],
                "recurrence_options": row_data["recurrence_options"],
                "base_rate": row_data["base_rate"],
                "base_fee": row_data["base_fee"],
                "min_charge": row_data["min_charge"],
                "travel_surcharge": row_data["travel_surcharge"],
                "status": Service.Status.ACTIVE,
            },
        )
        self._existing[row_data["code"]] = service
        return "created" if created else "updated"


# =============================================================
# Parse helpers
# =============================================================


def _parse_bool(value, default=False):
    if not value:
        return default
    return str(value).strip().lower() in ("true", "1", "yes")


def _parse_int(value, default=0):
    try:
        return int((value or "").strip() or default)
    except (ValueError, TypeError):
        return default


def _parse_decimal(value, default=Decimal("0.00")):
    try:
        return Decimal((value or "").strip() or "0")
    except (InvalidOperation, ValueError):
        return default


def _parse_semicolon_list(value):
    if not value:
        return []
    return [v.strip() for v in value.split(";") if v.strip()]


def _parse_recurrence_options(value):
    if not value or not value.strip():
        return {}
    result = {}
    for pair in value.split(";"):
        pair = pair.strip()
        if ":" in pair:
            key, val = pair.split(":", 1)
            try:
                result[key.strip()] = float(val.strip())
            except ValueError:
                pass
    return result
