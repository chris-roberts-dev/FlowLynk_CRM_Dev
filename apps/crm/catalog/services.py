"""
apps.crm.catalog.services — Catalog importer.

CSV format:
    code,name,item_type,description,base_duration_minutes,skill_tags,
    default_recurrence,recurrence_options,base_rate,base_fee,min_charge,
    travel_surcharge,allowed_addons,bundle_items

item_type: SERVICE, ADD_ON, PRODUCT, or BUNDLE
skill_tags: semicolon-separated (e.g. "carpet;hardwood;commercial")
recurrence_options: semicolon-separated pairs (e.g. "weekly:1.0;biweekly:1.05")
allowed_addons: semicolon-separated codes of ADD_ON items (e.g. "AO-WIN;AO-FRIDGE")
bundle_items: semicolon-separated codes of items in the bundle

Idempotent by (organization, code).
"""

import json
import logging
from decimal import Decimal, InvalidOperation

from apps.common.importing.models import ImportType
from apps.common.importing.services import BaseImporter
from apps.crm.catalog.models import CatalogItem, ItemType

logger = logging.getLogger(__name__)

VALID_ITEM_TYPES = {t.value for t in ItemType}


class CatalogImporter(BaseImporter):
    import_type = ImportType.CATALOG
    required_columns = {"code", "name", "item_type"}

    def __init__(self, organization, membership=None):
        super().__init__(organization, membership)
        self._existing_items = {}
        self._seen_codes = {}
        # Codes defined in this file, for addon/bundle reference validation
        self._file_codes = {}

    def pre_validate(self, reader):
        self._existing_items = {
            item.code: item
            for item in CatalogItem.unscoped_objects.filter(
                organization=self.organization
            )
        }

    def validate_row(self, line_num, row):
        code = (row.get("code") or "").strip()
        name = (row.get("name") or "").strip()
        item_type = (row.get("item_type") or "").strip().upper()

        # Required fields
        if not code:
            self.result.add_error(line_num, "", "Missing 'code'")
            return None
        if not name:
            self.result.add_error(line_num, code, "Missing 'name'")
            return None
        if item_type not in VALID_ITEM_TYPES:
            self.result.add_error(
                line_num,
                code,
                f"Invalid item_type '{item_type}'. Must be one of: {', '.join(sorted(VALID_ITEM_TYPES))}",
            )
            return None

        # Duplicate in file
        if code in self._seen_codes:
            self.result.add_error(
                line_num,
                code,
                f"Duplicate code '{code}' (first on line {self._seen_codes[code]}).",
            )
            return None
        self._seen_codes[code] = line_num
        self._file_codes[code] = item_type

        # Parse optional fields
        description = (row.get("description") or "").strip()
        base_duration = self._parse_int(row.get("base_duration_minutes"), 0)
        skill_tags = self._parse_semicolon_list(row.get("skill_tags"))
        default_recurrence = (
            (row.get("default_recurrence") or "ONE_TIME").strip().upper()
        )
        recurrence_options = self._parse_recurrence_options(
            row.get("recurrence_options")
        )
        base_rate = self._parse_decimal(row.get("base_rate"), Decimal("0"))
        base_fee = self._parse_decimal(row.get("base_fee"), Decimal("0"))
        min_charge = self._parse_decimal(row.get("min_charge"), Decimal("0"))
        travel_surcharge = (row.get("travel_surcharge") or "").strip().lower() in (
            "true",
            "1",
            "yes",
        )

        # Parse relationship refs (validated at apply time)
        allowed_addons = self._parse_semicolon_list(row.get("allowed_addons"))
        bundle_items = self._parse_semicolon_list(row.get("bundle_items"))

        # Validate addon refs exist (in file or DB)
        all_known_codes = set(self._existing_items.keys()) | set(
            self._file_codes.keys()
        )
        for addon_code in allowed_addons:
            if addon_code not in all_known_codes:
                self.result.add_error(
                    line_num, code, f"Unknown allowed_addon code '{addon_code}'"
                )
                return None

        for bi_code in bundle_items:
            if bi_code not in all_known_codes:
                self.result.add_error(
                    line_num, code, f"Unknown bundle_item code '{bi_code}'"
                )
                return None

        return {
            "_label": code,
            "code": code,
            "name": name,
            "item_type": item_type,
            "description": description,
            "base_duration_minutes": base_duration,
            "skill_tags": skill_tags,
            "default_recurrence": default_recurrence,
            "recurrence_options": recurrence_options,
            "base_rate": base_rate,
            "base_fee": base_fee,
            "min_charge": min_charge,
            "travel_surcharge": travel_surcharge,
            "allowed_addons": allowed_addons,
            "bundle_items": bundle_items,
        }

    def classify_row(self, row_data):
        existing = self._existing_items.get(row_data["code"])
        if existing is None:
            return "created"

        changed = (
            existing.name != row_data["name"]
            or existing.item_type != row_data["item_type"]
            or existing.description != row_data["description"]
            or existing.base_duration_minutes != row_data["base_duration_minutes"]
            or existing.base_rate != row_data["base_rate"]
            or existing.base_fee != row_data["base_fee"]
            or existing.min_charge != row_data["min_charge"]
        )
        return "updated" if changed else "unchanged"

    def apply_row(self, row_data):
        org = self.organization
        code = row_data["code"]

        item, created = CatalogItem.unscoped_objects.update_or_create(
            organization=org,
            code=code,
            defaults={
                "name": row_data["name"],
                "item_type": row_data["item_type"],
                "description": row_data["description"],
                "base_duration_minutes": row_data["base_duration_minutes"],
                "skill_tags": row_data["skill_tags"],
                "default_recurrence": row_data["default_recurrence"],
                "recurrence_options": row_data["recurrence_options"],
                "base_rate": row_data["base_rate"],
                "base_fee": row_data["base_fee"],
                "min_charge": row_data["min_charge"],
                "travel_surcharge": row_data["travel_surcharge"],
                "is_active": True,
            },
        )

        # Sync M2M relationships
        if row_data["allowed_addons"]:
            addons = CatalogItem.unscoped_objects.filter(
                organization=org, code__in=row_data["allowed_addons"]
            )
            item.allowed_addons.set(addons)
        else:
            item.allowed_addons.clear()

        if row_data["bundle_items"]:
            items = CatalogItem.unscoped_objects.filter(
                organization=org, code__in=row_data["bundle_items"]
            )
            item.bundle_items.set(items)
        else:
            item.bundle_items.clear()

        # Update cache
        self._existing_items[code] = item

        return "created" if created else "updated"

    # ── Parse helpers ────────────────────────

    @staticmethod
    def _parse_semicolon_list(value):
        if not value:
            return []
        return [v.strip() for v in value.split(";") if v.strip()]

    @staticmethod
    def _parse_int(value, default=0):
        try:
            return int((value or "").strip() or default)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_decimal(value, default=Decimal("0")):
        try:
            return Decimal((value or "").strip() or "0")
        except (InvalidOperation, ValueError):
            return default

    @staticmethod
    def _parse_recurrence_options(value):
        """Parse 'weekly:1.0;biweekly:1.05' into dict."""
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
