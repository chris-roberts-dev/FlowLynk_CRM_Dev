"""
Tests for apps.crm.locations + apps.common.importing — EPIC 5.

Validates:
- Region, Market, Location model CRUD and uniqueness
- Location hierarchy relationships
- Cross-org code uniqueness isolation
- LocationImporter dry-run and commit
- Idempotent double-import
- Parent chain validation (region before market, market before location)
- Error cases: missing fields, unknown parents, duplicates, bad header
- ImportRun tracking
"""

import pytest
from django.db import IntegrityError

from apps.common.importing.models import ImportRun, ImportStatus, ImportType
from apps.crm.locations.models import Location, Market, Region
from apps.crm.locations.services import LocationImporter
from apps.platform.organizations.models import OrganizationStatus


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────
@pytest.fixture
def active_org(make_organization):
    return make_organization(slug="acme", status=OrganizationStatus.ACTIVE)


@pytest.fixture
def region(active_org):
    return Region.unscoped_objects.create(
        organization=active_org, code="SE", name="Southeast"
    )


@pytest.fixture
def market(active_org, region):
    return Market.unscoped_objects.create(
        organization=active_org, code="ATL", name="Atlanta Metro", region=region
    )


@pytest.fixture
def location(active_org, market):
    return Location.unscoped_objects.create(
        organization=active_org,
        code="ATL-001",
        name="Atlanta North",
        market=market,
        city="Atlanta",
        state="GA",
        timezone="America/New_York",
    )


SAMPLE_CSV = """level,code,name,parent_code,street,city,state,postal_code,country,timezone
REGION,SE,Southeast,,,,,,US,
REGION,NE,Northeast,,,,,,US,
MARKET,ATL,Atlanta Metro,SE,,,,,US,
MARKET,NYC,New York City,NE,,,,,US,
LOCATION,ATL-001,Atlanta North,ATL,123 Main St,Atlanta,GA,30301,US,America/New_York
LOCATION,ATL-002,Atlanta South,ATL,456 Oak Ave,Atlanta,GA,30302,US,America/New_York
LOCATION,NYC-001,Manhattan Office,NYC,789 Broadway,New York,NY,10001,US,America/New_York
"""


# ──────────────────────────────────────────────
# Model tests
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestRegionModel:

    def test_create(self, region):
        assert region.pk is not None
        assert region.code == "SE"
        assert region.is_active is True

    def test_org_code_unique(self, active_org, region):
        with pytest.raises(IntegrityError):
            Region.unscoped_objects.create(
                organization=active_org, code="SE", name="Dup"
            )

    def test_same_code_different_orgs(self, active_org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        Region.unscoped_objects.create(organization=active_org, code="X", name="X1")
        r2 = Region.unscoped_objects.create(organization=org_b, code="X", name="X2")
        assert r2.pk is not None

    def test_str(self, region):
        assert str(region) == "Southeast (SE)"


@pytest.mark.django_db
class TestMarketModel:

    def test_create(self, market, region):
        assert market.pk is not None
        assert market.region == region

    def test_org_code_unique(self, active_org, market, region):
        with pytest.raises(IntegrityError):
            Market.unscoped_objects.create(
                organization=active_org, code="ATL", name="Dup", region=region
            )

    def test_region_markets_relation(self, region, market):
        assert market in region.markets.all()

    def test_str(self, market):
        assert str(market) == "Atlanta Metro (ATL)"


@pytest.mark.django_db
class TestLocationModel:

    def test_create(self, location, market):
        assert location.pk is not None
        assert location.market == market
        assert location.city == "Atlanta"

    def test_full_hierarchy(self, location):
        assert location.full_hierarchy == "Southeast > Atlanta Metro > Atlanta North"

    def test_hierarchy_no_market(self, active_org):
        loc = Location.unscoped_objects.create(
            organization=active_org, code="SOLO", name="Standalone"
        )
        assert loc.full_hierarchy == "Standalone"

    def test_org_code_unique(self, active_org, location, market):
        with pytest.raises(IntegrityError):
            Location.unscoped_objects.create(
                organization=active_org, code="ATL-001", name="Dup", market=market
            )

    def test_str(self, location):
        assert str(location) == "Atlanta North (ATL-001)"


# ──────────────────────────────────────────────
# LocationImporter: dry-run
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLocationImporterDryRun:

    def test_dry_run_shows_creates(self, active_org):
        importer = LocationImporter(organization=active_org)
        result = importer.run(SAMPLE_CSV, dry_run=True)

        assert not result.has_errors
        assert len(result.created) == 7  # 2 regions + 2 markets + 3 locations
        assert Region.unscoped_objects.filter(organization=active_org).count() == 0

    def test_dry_run_detects_updates(self, active_org):
        # Pre-create a region with different name
        Region.unscoped_objects.create(
            organization=active_org, code="SE", name="Old Name"
        )

        importer = LocationImporter(organization=active_org)
        result = importer.run(SAMPLE_CSV, dry_run=True)

        assert not result.has_errors
        assert "SE" in result.updated

    def test_dry_run_detects_unchanged(self, active_org):
        Region.unscoped_objects.create(
            organization=active_org, code="SE", name="Southeast"
        )

        importer = LocationImporter(organization=active_org)
        result = importer.run(SAMPLE_CSV, dry_run=True)

        assert "SE" in result.unchanged

    def test_dry_run_creates_import_run(self, active_org):
        importer = LocationImporter(organization=active_org)
        importer.run(SAMPLE_CSV, dry_run=True, file_name="test.csv")

        run = ImportRun.objects.filter(organization=active_org).first()
        assert run is not None
        assert run.status == ImportStatus.DRY_RUN
        assert run.is_dry_run is True
        assert run.file_name == "test.csv"


# ──────────────────────────────────────────────
# LocationImporter: commit
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLocationImporterCommit:

    def test_creates_full_hierarchy(self, active_org):
        importer = LocationImporter(organization=active_org)
        result = importer.run(SAMPLE_CSV, dry_run=False)

        assert not result.has_errors
        assert Region.unscoped_objects.filter(organization=active_org).count() == 2
        assert Market.unscoped_objects.filter(organization=active_org).count() == 2
        assert Location.unscoped_objects.filter(organization=active_org).count() == 3

    def test_parent_chain_correct(self, active_org):
        importer = LocationImporter(organization=active_org)
        importer.run(SAMPLE_CSV, dry_run=False)

        atl = Location.unscoped_objects.get(organization=active_org, code="ATL-001")
        assert atl.market.code == "ATL"
        assert atl.market.region.code == "SE"

    def test_address_fields_populated(self, active_org):
        importer = LocationImporter(organization=active_org)
        importer.run(SAMPLE_CSV, dry_run=False)

        loc = Location.unscoped_objects.get(organization=active_org, code="ATL-001")
        assert loc.street == "123 Main St"
        assert loc.city == "Atlanta"
        assert loc.state == "GA"
        assert loc.postal_code == "30301"
        assert loc.timezone == "America/New_York"

    def test_idempotent_double_import(self, active_org):
        importer = LocationImporter(organization=active_org)
        result1 = importer.run(SAMPLE_CSV, dry_run=False)

        importer2 = LocationImporter(organization=active_org)
        result2 = importer2.run(SAMPLE_CSV, dry_run=False)

        assert len(result1.created) == 7
        # Second import: everything should be unchanged (or "updated" due to update_or_create)
        assert len(result2.created) == 0
        assert Region.unscoped_objects.filter(organization=active_org).count() == 2

    def test_update_existing_name(self, active_org):
        # First import
        importer = LocationImporter(organization=active_org)
        importer.run(SAMPLE_CSV, dry_run=False)

        # Modified CSV with changed name
        updated_csv = SAMPLE_CSV.replace("Atlanta Metro", "Greater Atlanta")
        importer2 = LocationImporter(organization=active_org)
        result2 = importer2.run(updated_csv, dry_run=False)

        market = Market.unscoped_objects.get(organization=active_org, code="ATL")
        assert market.name == "Greater Atlanta"
        assert "ATL" in result2.updated

    def test_commit_creates_import_run(self, active_org):
        importer = LocationImporter(organization=active_org)
        importer.run(SAMPLE_CSV, dry_run=False, file_name="locations.csv")

        run = ImportRun.objects.filter(organization=active_org).first()
        assert run.status == ImportStatus.COMMITTED
        assert run.is_dry_run is False
        assert run.created_count == 7


# ──────────────────────────────────────────────
# Cross-org isolation
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLocationImporterIsolation:

    def test_import_does_not_affect_other_org(self, active_org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)

        # Import into org_a
        LocationImporter(organization=active_org).run(SAMPLE_CSV, dry_run=False)

        # org_b should have nothing
        assert Region.unscoped_objects.filter(organization=org_b).count() == 0
        assert Location.unscoped_objects.filter(organization=org_b).count() == 0

    def test_same_codes_in_different_orgs(self, active_org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)

        LocationImporter(organization=active_org).run(SAMPLE_CSV, dry_run=False)
        LocationImporter(organization=org_b).run(SAMPLE_CSV, dry_run=False)

        assert Region.unscoped_objects.filter(code="SE").count() == 2
        assert (
            Region.unscoped_objects.filter(code="SE", organization=active_org).count()
            == 1
        )
        assert (
            Region.unscoped_objects.filter(code="SE", organization=org_b).count() == 1
        )


# ──────────────────────────────────────────────
# Error cases
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestLocationImporterErrors:

    def test_missing_required_columns(self, active_org):
        bad_csv = "wrong,columns\na,b\n"
        result = LocationImporter(organization=active_org).run(bad_csv, dry_run=True)
        assert result.has_errors
        assert any("Missing required columns" in e["error"] for e in result.errors)

    def test_missing_code(self, active_org):
        csv = "level,code,name,parent_code\nREGION,,No Code,\n"
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("Missing 'code'" in e["error"] for e in result.errors)

    def test_missing_name(self, active_org):
        csv = "level,code,name,parent_code\nREGION,SE,,\n"
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("Missing 'name'" in e["error"] for e in result.errors)

    def test_invalid_level(self, active_org):
        csv = "level,code,name,parent_code\nINVALID,X,Bad Level,\n"
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("Invalid level" in e["error"] for e in result.errors)

    def test_market_without_parent(self, active_org):
        csv = "level,code,name,parent_code\nMARKET,ATL,Atlanta,\n"
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("require a parent_code" in e["error"] for e in result.errors)

    def test_location_without_parent(self, active_org):
        csv = "level,code,name,parent_code\nLOCATION,L1,Orphan,\n"
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors

    def test_unknown_parent_region(self, active_org):
        csv = "level,code,name,parent_code\nMARKET,ATL,Atlanta,NONEXISTENT\n"
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("Unknown region code" in e["error"] for e in result.errors)

    def test_unknown_parent_market(self, active_org):
        csv = (
            "level,code,name,parent_code\nREGION,SE,Southeast,\nLOCATION,L1,Loc,NOPE\n"
        )
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("Unknown market code" in e["error"] for e in result.errors)

    def test_duplicate_code_in_file(self, active_org):
        csv = (
            "level,code,name,parent_code\n"
            "REGION,SE,Southeast,\n"
            "REGION,SE,Southeast Again,\n"
        )
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("Duplicate" in e["error"] for e in result.errors)

    def test_region_with_parent_code_rejected(self, active_org):
        csv = "level,code,name,parent_code\nREGION,SE,Southeast,PARENT\n"
        result = LocationImporter(organization=active_org).run(csv, dry_run=True)
        assert result.has_errors
        assert any("must not have a parent_code" in e["error"] for e in result.errors)

    def test_errors_stop_commit(self, active_org):
        """Validation errors should prevent any DB changes even in commit mode."""
        csv = (
            "level,code,name,parent_code\n"
            "REGION,SE,Southeast,\n"
            "MARKET,ATL,Atlanta,NONEXISTENT\n"
        )
        result = LocationImporter(organization=active_org).run(csv, dry_run=False)
        assert result.has_errors
        # SE region should NOT have been created because errors stop processing
        assert Region.unscoped_objects.filter(organization=active_org).count() == 0

    def test_empty_csv(self, active_org):
        result = LocationImporter(organization=active_org).run("", dry_run=True)
        assert result.has_errors


# ──────────────────────────────────────────────
# ImportRun model
# ──────────────────────────────────────────────
@pytest.mark.django_db
class TestImportRunModel:

    def test_import_run_created(self, active_org):
        LocationImporter(organization=active_org).run(SAMPLE_CSV, dry_run=True)
        assert ImportRun.objects.filter(organization=active_org).count() == 1

    def test_import_run_tracks_counts(self, active_org):
        LocationImporter(organization=active_org).run(SAMPLE_CSV, dry_run=False)

        run = ImportRun.objects.filter(organization=active_org).first()
        assert run.created_count == 7
        assert run.error_count == 0

    def test_import_run_tracks_errors(self, active_org):
        bad_csv = "level,code,name,parent_code\nMARKET,ATL,Atlanta,\n"
        LocationImporter(organization=active_org).run(bad_csv, dry_run=True)

        run = ImportRun.objects.filter(organization=active_org).first()
        assert run.error_count > 0
        assert len(run.errors_json) > 0

    def test_import_run_str(self, active_org):
        LocationImporter(organization=active_org).run(
            SAMPLE_CSV, dry_run=True, file_name="locs.csv"
        )
        run = ImportRun.objects.first()
        assert "locs.csv" in str(run)
        assert "dry-run" in str(run)
