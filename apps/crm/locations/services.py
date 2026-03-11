"""
apps.crm.locations.services — Location hierarchy importer.

CSV format:
    level,code,name,parent_code,street,city,state,postal_code,country,timezone

level: REGION, MARKET, or LOCATION
parent_code:
  - REGION: (empty)
  - MARKET: region code
  - LOCATION: market code

Idempotent by (organization, code) per level.
Validates parent chain within the same org.
"""

import logging

from apps.common.importing.models import ImportType
from apps.common.importing.services import BaseImporter
from apps.crm.locations.models import Location, Market, Region

logger = logging.getLogger(__name__)


class LocationImporter(BaseImporter):
    import_type = ImportType.LOCATIONS
    required_columns = {"level", "code", "name"}

    def __init__(self, organization, membership=None):
        super().__init__(organization, membership)
        # Lookup caches populated in pre_validate
        self._existing_regions = {}
        self._existing_markets = {}
        self._existing_locations = {}
        # Track codes defined earlier in the same file
        self._file_regions = {}
        self._file_markets = {}
        self._seen_codes = {}  # {(level, code): line_num} for duplicate detection

    def pre_validate(self, reader):
        """Load existing records for idempotency classification."""
        org = self.organization

        self._existing_regions = {
            r.code: r for r in Region.unscoped_objects.filter(organization=org)
        }
        self._existing_markets = {
            m.code: m
            for m in Market.unscoped_objects.filter(organization=org).select_related(
                "region"
            )
        }
        self._existing_locations = {
            loc.code: loc
            for loc in Location.unscoped_objects.filter(
                organization=org
            ).select_related("market")
        }

    def validate_row(self, line_num, row):
        level = (row.get("level") or "").strip().upper()
        code = (row.get("code") or "").strip()
        name = (row.get("name") or "").strip()
        parent_code = (row.get("parent_code") or "").strip()

        # Required fields
        if not code:
            self.result.add_error(line_num, "", "Missing 'code'")
            return None
        if not name:
            self.result.add_error(line_num, code, "Missing 'name'")
            return None
        if level not in ("REGION", "MARKET", "LOCATION"):
            self.result.add_error(
                line_num,
                code,
                f"Invalid level '{level}'. Must be REGION, MARKET, or LOCATION.",
            )
            return None

        # Duplicate check within file
        dup_key = (level, code)
        if dup_key in self._seen_codes:
            self.result.add_error(
                line_num,
                code,
                f"Duplicate {level} code '{code}' (first seen on line {self._seen_codes[dup_key]}).",
            )
            return None
        self._seen_codes[dup_key] = line_num

        # Parent validation
        if level == "REGION":
            if parent_code:
                self.result.add_error(
                    line_num, code, "Regions must not have a parent_code."
                )
                return None
            self._file_regions[code] = name

        elif level == "MARKET":
            if not parent_code:
                self.result.add_error(
                    line_num, code, "Markets require a parent_code (region code)."
                )
                return None
            if (
                parent_code not in self._existing_regions
                and parent_code not in self._file_regions
            ):
                self.result.add_error(
                    line_num,
                    code,
                    f"Unknown region code '{parent_code}'. Regions must be defined before markets.",
                )
                return None
            self._file_markets[code] = {"parent_code": parent_code, "name": name}

        elif level == "LOCATION":
            if not parent_code:
                self.result.add_error(
                    line_num, code, "Locations require a parent_code (market code)."
                )
                return None
            if (
                parent_code not in self._existing_markets
                and parent_code not in self._file_markets
            ):
                self.result.add_error(
                    line_num,
                    code,
                    f"Unknown market code '{parent_code}'. Markets must be defined before locations.",
                )
                return None

        return {
            "_label": code,
            "level": level,
            "code": code,
            "name": name,
            "parent_code": parent_code,
            "street": (row.get("street") or "").strip(),
            "city": (row.get("city") or "").strip(),
            "state": (row.get("state") or "").strip(),
            "postal_code": (row.get("postal_code") or "").strip(),
            "country": (row.get("country") or "US").strip(),
            "timezone": (row.get("timezone") or "").strip(),
        }

    def classify_row(self, row_data):
        """Determine if this row would create, update, or leave unchanged."""
        level = row_data["level"]
        code = row_data["code"]

        if level == "REGION":
            existing = self._existing_regions.get(code)
            if existing is None:
                return "created"
            if existing.name != row_data["name"]:
                return "updated"
            return "unchanged"

        elif level == "MARKET":
            existing = self._existing_markets.get(code)
            if existing is None:
                return "created"
            changed = (
                existing.name != row_data["name"]
                or existing.region.code != row_data["parent_code"]
            )
            return "updated" if changed else "unchanged"

        elif level == "LOCATION":
            existing = self._existing_locations.get(code)
            if existing is None:
                return "created"
            changed = (
                existing.name != row_data["name"]
                or (existing.market and existing.market.code) != row_data["parent_code"]
                or existing.street != row_data["street"]
                or existing.city != row_data["city"]
                or existing.state != row_data["state"]
                or existing.postal_code != row_data["postal_code"]
                or existing.timezone != row_data["timezone"]
            )
            return "updated" if changed else "unchanged"

        return "unchanged"

    def apply_row(self, row_data):
        """Create or update a single hierarchy record."""
        level = row_data["level"]
        code = row_data["code"]
        org = self.organization

        if level == "REGION":
            region, created = Region.unscoped_objects.update_or_create(
                organization=org,
                code=code,
                defaults={"name": row_data["name"], "is_active": True},
            )
            # Update local cache for later market/location rows
            self._existing_regions[code] = region
            return "created" if created else "updated"

        elif level == "MARKET":
            region = self._existing_regions[row_data["parent_code"]]
            market, created = Market.unscoped_objects.update_or_create(
                organization=org,
                code=code,
                defaults={
                    "name": row_data["name"],
                    "region": region,
                    "is_active": True,
                },
            )
            self._existing_markets[code] = market
            return "created" if created else "updated"

        elif level == "LOCATION":
            market = self._existing_markets[row_data["parent_code"]]
            defaults = {
                "name": row_data["name"],
                "market": market,
                "is_active": True,
                "street": row_data["street"],
                "city": row_data["city"],
                "state": row_data["state"],
                "postal_code": row_data["postal_code"],
                "country": row_data["country"],
                "timezone": row_data["timezone"],
            }
            location, created = Location.unscoped_objects.update_or_create(
                organization=org,
                code=code,
                defaults=defaults,
            )
            self._existing_locations[code] = location
            return "created" if created else "updated"

        return "unchanged"
