"""
Tests for apps.crm.catalog — Holistic Products & Services.

Validates:
- UnitOfMeasure, Supplier, Category models
- Product CRUD, SKU auto-generation, uniqueness, BOM, supplier links
- Service CRUD, code uniqueness, checklists
- ProductImporter and ServiceImporter (dry-run, commit, idempotency, errors)
- Cross-org isolation
"""

import pytest
from decimal import Decimal
from django.db import IntegrityError

from apps.common.importing.models import ImportRun
from apps.crm.catalog.models import (
    ChecklistItem,
    ChecklistTemplate,
    Material,
    Product,
    ProductCategory,
    ProductComponent,
    ProductSupplierLink,
    Service,
    ServiceCategory,
    Supplier,
    UnitOfMeasure,
)
from apps.crm.catalog.services import ProductImporter, ServiceImporter
from apps.platform.organizations.models import OrganizationStatus


@pytest.fixture
def org(make_organization):
    return make_organization(slug="acme", status=OrganizationStatus.ACTIVE)


@pytest.fixture
def uom_each(org):
    return UnitOfMeasure.unscoped_objects.create(
        organization=org, code="EA", name="Each"
    )


@pytest.fixture
def uom_hour(org):
    return UnitOfMeasure.unscoped_objects.create(
        organization=org, code="HR", name="Hour", is_fractional=True, precision=2
    )


@pytest.fixture
def supplier(org):
    return Supplier.unscoped_objects.create(
        organization=org, name="Acme Supplies", code="ACME-SUP"
    )


@pytest.fixture
def product(org, uom_each):
    return Product.unscoped_objects.create(
        organization=org,
        name="Floor Cleaner",
        sku="PROD-FLOOR",
        item_type=Product.ItemType.STOCK,
        default_price=Decimal("12.99"),
        unit_of_measure=uom_each,
    )


@pytest.fixture
def service(org):
    return Service.unscoped_objects.create(
        organization=org,
        code="SVC-STD",
        name="Standard Cleaning",
        base_duration_minutes=90,
        base_rate=Decimal("45.00"),
        base_fee=Decimal("25.00"),
    )


# =============================================================
# UnitOfMeasure
# =============================================================
@pytest.mark.django_db
class TestUnitOfMeasure:
    def test_create(self, uom_each):
        assert uom_each.pk is not None
        assert uom_each.code == "EA"
        assert uom_each.is_fractional is False

    def test_fractional_requires_precision(self, org):
        from django.core.exceptions import ValidationError

        uom = UnitOfMeasure(
            organization=org, code="GAL", name="Gallon", is_fractional=True, precision=0
        )
        with pytest.raises(ValidationError):
            uom.clean()

    def test_org_code_unique(self, org, uom_each):
        with pytest.raises(IntegrityError):
            UnitOfMeasure.unscoped_objects.create(
                organization=org, code="EA", name="Each2"
            )


# =============================================================
# Supplier
# =============================================================
@pytest.mark.django_db
class TestSupplier:
    def test_create(self, supplier):
        assert supplier.code == "ACME-SUP"

    def test_org_name_unique(self, org, supplier):
        with pytest.raises(IntegrityError):
            Supplier.unscoped_objects.create(organization=org, name="Acme Supplies")


# =============================================================
# ProductCategory
# =============================================================
@pytest.mark.django_db
class TestProductCategory:
    def test_create(self, org):
        cat = ProductCategory.unscoped_objects.create(
            organization=org, name="Cleaning Supplies"
        )
        assert cat.slug == "cleaning-supplies"

    def test_parent_child(self, org):
        parent = ProductCategory.unscoped_objects.create(
            organization=org, name="Supplies"
        )
        child = ProductCategory.unscoped_objects.create(
            organization=org, name="Floor", parent=parent
        )
        assert child.parent == parent

    def test_self_parent_rejected(self, org):
        from django.core.exceptions import ValidationError

        cat = ProductCategory.unscoped_objects.create(organization=org, name="Loop")
        cat.parent = cat
        with pytest.raises(ValidationError):
            cat.clean()


# =============================================================
# Product
# =============================================================
@pytest.mark.django_db
class TestProduct:
    def test_create(self, product):
        assert product.pk is not None
        assert product.sku == "PROD-FLOOR"
        assert product.default_price == Decimal("12.99")

    def test_auto_sku(self, org):
        p = Product.unscoped_objects.create(organization=org, name="Auto SKU Product")
        assert p.sku  # Should have been auto-generated
        assert len(p.sku) > 5

    def test_org_sku_unique(self, org, product):
        with pytest.raises(IntegrityError):
            Product.unscoped_objects.create(
                organization=org, name="Dup", sku="PROD-FLOOR"
            )

    def test_same_sku_different_orgs(self, org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        Product.unscoped_objects.create(
            organization=org_b, name="Same", sku="PROD-FLOOR"
        )

    def test_bundle_items_m2m(self, org, product):
        addon = Product.unscoped_objects.create(
            organization=org,
            name="Addon",
            sku="PROD-ADDON",
            item_type=Product.ItemType.ADD_ON,
        )
        bundle = Product.unscoped_objects.create(
            organization=org,
            name="Bundle",
            sku="BDL-ALL",
            item_type=Product.ItemType.BUNDLE,
        )
        bundle.bundle_items.set([product, addon])
        assert bundle.bundle_items.count() == 2

    def test_str(self, product):
        assert "PROD-FLOOR" in str(product)

    def test_supplier_link(self, product, supplier, org):
        link = ProductSupplierLink.unscoped_objects.create(
            organization=org,
            product=product,
            supplier=supplier,
            is_preferred=True,
            last_cost=Decimal("8.50"),
        )
        assert link.is_preferred is True
        assert product.supplier_links.count() == 1

    def test_component_bom(self, org, product):
        raw = Product.unscoped_objects.create(
            organization=org,
            name="Chemical Base",
            sku="RAW-CHEM",
            source_type=Product.SourceType.PURCHASED,
        )
        comp = ProductComponent.unscoped_objects.create(
            organization=org,
            parent_product=product,
            component_product=raw,
            quantity_required=Decimal("2.5"),
        )
        assert product.components.count() == 1


# =============================================================
# Service
# =============================================================
@pytest.mark.django_db
class TestService:
    def test_create(self, service):
        assert service.pk is not None
        assert service.code == "SVC-STD"
        assert service.base_duration_minutes == 90

    def test_org_code_unique(self, org, service):
        with pytest.raises(IntegrityError):
            Service.unscoped_objects.create(
                organization=org, code="SVC-STD", name="Dup"
            )

    def test_same_code_different_orgs(self, org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        Service.unscoped_objects.create(
            organization=org_b, code="SVC-STD", name="Other"
        )

    def test_allowed_addons(self, org, service):
        addon = Service.unscoped_objects.create(
            organization=org, code="SVC-WIN", name="Window Cleaning"
        )
        service.allowed_addons.add(addon)
        assert addon in service.allowed_addons.all()

    def test_required_products(self, org, service, product):
        service.required_products.add(product)
        assert product in service.required_products.all()

    def test_str(self, service):
        assert "Standard Cleaning" in str(service)
        assert "SVC-STD" in str(service)


# =============================================================
# Checklists (linked to Service)
# =============================================================
@pytest.mark.django_db
class TestChecklists:
    def test_create_template(self, org, service):
        t = ChecklistTemplate.objects.create(
            organization=org, service=service, name="Standard Checklist"
        )
        assert t.version == 1

    def test_checklist_items(self, org, service):
        t = ChecklistTemplate.objects.create(
            organization=org, service=service, name="Checklist"
        )
        ChecklistItem.objects.create(
            template=t, order=1, description="Vacuum", is_required=True
        )
        ChecklistItem.objects.create(
            template=t, order=2, description="Dust", is_required=True
        )
        ChecklistItem.objects.create(
            template=t, order=3, description="Mirrors", is_required=False
        )
        assert t.item_count == 3

    def test_version_unique_per_service(self, org, service):
        ChecklistTemplate.objects.create(
            organization=org, service=service, name="V1", version=1
        )
        with pytest.raises(IntegrityError):
            ChecklistTemplate.objects.create(
                organization=org, service=service, name="V1b", version=1
            )


# =============================================================
# Material
# =============================================================
@pytest.mark.django_db
class TestMaterial:
    def test_create(self, org, uom_each):
        m = Material.unscoped_objects.create(
            organization=org,
            name="Cleaning Fluid",
            sku="MAT-FLUID",
            unit_of_measure=uom_each,
            unit_cost=Decimal("3.50"),
        )
        assert m.sku == "MAT-FLUID"

    def test_sku_unique(self, org, uom_each):
        Material.unscoped_objects.create(
            organization=org, name="A", sku="MAT-A", unit_of_measure=uom_each
        )
        with pytest.raises(IntegrityError):
            Material.unscoped_objects.create(
                organization=org, name="B", sku="MAT-A", unit_of_measure=uom_each
            )


# =============================================================
# Product Importer
# =============================================================
PRODUCT_CSV = """sku,name,item_type,description,default_cost,default_price,is_sellable
PROD-A,Floor Cleaner,STOCK,Best cleaner,5.00,12.99,true
PROD-B,Mop Head,STOCK,Replacement mop,2.50,7.99,true
PROD-C,Gift Card,NON_STOCK,Gift card,0,25.00,true
"""


@pytest.mark.django_db
class TestProductImporterDryRun:
    def test_shows_creates(self, org):
        result = ProductImporter(organization=org).run(PRODUCT_CSV, dry_run=True)
        assert not result.has_errors
        assert len(result.created) == 3
        assert Product.unscoped_objects.filter(organization=org).count() == 0

    def test_detects_updates(self, org):
        Product.unscoped_objects.create(organization=org, name="Old Name", sku="PROD-A")
        result = ProductImporter(organization=org).run(PRODUCT_CSV, dry_run=True)
        assert "PROD-A" in result.updated


@pytest.mark.django_db
class TestProductImporterCommit:
    def test_creates_all(self, org):
        result = ProductImporter(organization=org).run(PRODUCT_CSV, dry_run=False)
        assert len(result.created) == 3
        assert Product.unscoped_objects.filter(organization=org).count() == 3

    def test_fields_populated(self, org):
        ProductImporter(organization=org).run(PRODUCT_CSV, dry_run=False)
        p = Product.unscoped_objects.get(organization=org, sku="PROD-A")
        assert p.name == "Floor Cleaner"
        assert p.default_price == Decimal("12.99")
        assert p.default_cost == Decimal("5.00")
        assert p.is_sellable is True

    def test_idempotent(self, org):
        ProductImporter(organization=org).run(PRODUCT_CSV, dry_run=False)
        r2 = ProductImporter(organization=org).run(PRODUCT_CSV, dry_run=False)
        assert len(r2.created) == 0
        assert Product.unscoped_objects.filter(organization=org).count() == 3

    def test_auto_sku_when_blank(self, org):
        csv = "sku,name,item_type\n,Auto Product,STOCK\n"
        result = ProductImporter(organization=org).run(csv, dry_run=False)
        assert len(result.created) == 1
        p = Product.unscoped_objects.filter(organization=org).first()
        assert p.sku  # Auto-generated


@pytest.mark.django_db
class TestProductImporterErrors:
    def test_missing_name(self, org):
        csv = "sku,name,item_type\nX,,STOCK\n"
        result = ProductImporter(organization=org).run(csv, dry_run=True)
        assert result.has_errors

    def test_invalid_item_type(self, org):
        csv = "sku,name,item_type\nX,Test,INVALID\n"
        result = ProductImporter(organization=org).run(csv, dry_run=True)
        assert result.has_errors

    def test_duplicate_sku_in_file(self, org):
        csv = "sku,name,item_type\nX,First,STOCK\nX,Second,STOCK\n"
        result = ProductImporter(organization=org).run(csv, dry_run=True)
        assert result.has_errors


# =============================================================
# Service Importer
# =============================================================
SERVICE_CSV = """code,name,description,base_duration_minutes,base_rate,base_fee,min_charge,travel_surcharge,skill_tags,default_recurrence,recurrence_options
SVC-STD,Standard Cleaning,Full cleaning,90,45.00,25.00,50.00,true,carpet;hardwood,WEEKLY,weekly:1.0;biweekly:1.05
SVC-DEEP,Deep Cleaning,Deep clean,180,85.00,35.00,75.00,true,carpet;commercial,ONE_TIME,
SVC-WIN,Window Cleaning,Windows,30,15.00,0,0,false,glass,,
"""


@pytest.mark.django_db
class TestServiceImporterDryRun:
    def test_shows_creates(self, org):
        result = ServiceImporter(organization=org).run(SERVICE_CSV, dry_run=True)
        assert not result.has_errors
        assert len(result.created) == 3
        assert Service.unscoped_objects.filter(organization=org).count() == 0


@pytest.mark.django_db
class TestServiceImporterCommit:
    def test_creates_all(self, org):
        result = ServiceImporter(organization=org).run(SERVICE_CSV, dry_run=False)
        assert len(result.created) == 3

    def test_fields_populated(self, org):
        ServiceImporter(organization=org).run(SERVICE_CSV, dry_run=False)
        s = Service.unscoped_objects.get(organization=org, code="SVC-STD")
        assert s.name == "Standard Cleaning"
        assert s.base_rate == Decimal("45.00")
        assert s.base_fee == Decimal("25.00")
        assert s.base_duration_minutes == 90
        assert s.travel_surcharge is True
        assert "carpet" in s.skill_tags
        assert s.recurrence_options.get("weekly") == 1.0

    def test_idempotent(self, org):
        ServiceImporter(organization=org).run(SERVICE_CSV, dry_run=False)
        r2 = ServiceImporter(organization=org).run(SERVICE_CSV, dry_run=False)
        assert len(r2.created) == 0

    def test_update_existing(self, org):
        ServiceImporter(organization=org).run(SERVICE_CSV, dry_run=False)
        updated = SERVICE_CSV.replace("Standard Cleaning", "Premium Cleaning")
        r2 = ServiceImporter(organization=org).run(updated, dry_run=False)
        assert "SVC-STD" in r2.updated
        s = Service.unscoped_objects.get(organization=org, code="SVC-STD")
        assert s.name == "Premium Cleaning"


@pytest.mark.django_db
class TestServiceImporterErrors:
    def test_missing_code(self, org):
        csv = "code,name\n,No Code\n"
        result = ServiceImporter(organization=org).run(csv, dry_run=True)
        assert result.has_errors

    def test_missing_name(self, org):
        csv = "code,name\nSVC,\n"
        result = ServiceImporter(organization=org).run(csv, dry_run=True)
        assert result.has_errors

    def test_duplicate_code(self, org):
        csv = "code,name\nSVC,First\nSVC,Second\n"
        result = ServiceImporter(organization=org).run(csv, dry_run=True)
        assert result.has_errors


# =============================================================
# Cross-org isolation
# =============================================================
@pytest.mark.django_db
class TestCatalogIsolation:
    def test_products_isolated(self, org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        ProductImporter(organization=org).run(PRODUCT_CSV, dry_run=False)
        assert Product.unscoped_objects.filter(organization=org_b).count() == 0

    def test_services_isolated(self, org, make_organization):
        org_b = make_organization(slug="beta", status=OrganizationStatus.ACTIVE)
        ServiceImporter(organization=org).run(SERVICE_CSV, dry_run=False)
        assert Service.unscoped_objects.filter(organization=org_b).count() == 0
