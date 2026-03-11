"""
apps.crm.catalog.admin — Products, Services, and supporting entity admin.

Products: full inventory/supplier management with CSV import.
Services: recurring offerings with checklists and CSV import.
Supporting: UnitOfMeasure, Supplier, Categories, Materials.
"""

from django.contrib import admin

from apps.common.admin import TenantScopedAdmin, flowlynk_admin_site
from apps.common.admin.import_mixin import ImportCSVMixin
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


# =============================================================
# SUPPORTING ENTITIES
# =============================================================


@admin.register(UnitOfMeasure, site=flowlynk_admin_site)
class UnitOfMeasureAdmin(TenantScopedAdmin):
    list_display = ("code", "name", "is_fractional", "precision", "is_active")
    list_filter = ("is_active", "is_fractional")
    search_fields = ("code", "name")


@admin.register(Supplier, site=flowlynk_admin_site)
class SupplierAdmin(TenantScopedAdmin):
    list_display = ("name", "code", "contact_name", "email", "phone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "contact_name", "email")
    fieldsets = (
        (None, {"fields": ("name", "code", "is_active")}),
        ("Contact", {"fields": ("contact_name", "email", "phone", "website")}),
        ("Business", {"fields": ("payment_terms", "account_number")}),
        (
            "Address",
            {
                "fields": ("street", "city", "state", "postal_code", "country"),
                "classes": ("collapse",),
            },
        ),
        ("Notes", {"fields": ("notes",)}),
    )


@admin.register(ProductCategory, site=flowlynk_admin_site)
class ProductCategoryAdmin(TenantScopedAdmin):
    list_display = ("name", "slug", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            org = getattr(request, "organization", None)
            if org:
                kwargs["queryset"] = ProductCategory.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ServiceCategory, site=flowlynk_admin_site)
class ServiceCategoryAdmin(TenantScopedAdmin):
    list_display = ("name", "slug", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            org = getattr(request, "organization", None)
            if org:
                kwargs["queryset"] = ServiceCategory.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# =============================================================
# PRODUCT
# =============================================================


class ProductSupplierLinkInline(admin.TabularInline):
    model = ProductSupplierLink
    extra = 0
    fields = ("supplier", "supplier_sku", "is_preferred", "last_cost", "lead_time_days")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "supplier":
            org = getattr(request, "organization", None)
            if org:
                kwargs["queryset"] = Supplier.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class ProductComponentInline(admin.TabularInline):
    model = ProductComponent
    fk_name = "parent_product"
    extra = 0
    fields = ("component_product", "quantity_required", "notes")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "component_product":
            org = getattr(request, "organization", None)
            if org:
                kwargs["queryset"] = Product.unscoped_objects.filter(
                    organization=org, status=Product.Status.ACTIVE
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Product, site=flowlynk_admin_site)
class ProductAdmin(ImportCSVMixin, TenantScopedAdmin):
    # Import
    import_url_name = "product-import"
    import_button_label = "Import Products CSV"
    import_page_title = "Import Products"
    change_list_template = "admin/import_changelist.html"

    def get_importer(self, organization, membership=None):
        from apps.crm.catalog.services import ProductImporter

        return ProductImporter(organization=organization, membership=membership)

    # Standard config
    list_display = (
        "name",
        "sku",
        "item_type",
        "status",
        "default_price",
        "default_cost",
        "tracking_type",
        "is_sellable",
    )
    list_filter = (
        "item_type",
        "status",
        "source_type",
        "tracking_type",
        "is_sellable",
        "is_consumable",
        "category",
    )
    search_fields = ("name", "sku", "barcode", "description")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ProductSupplierLinkInline, ProductComponentInline]

    fieldsets = (
        (
            None,
            {"fields": ("name", "sku", "barcode", "category", "description", "status")},
        ),
        (
            "Classification",
            {
                "fields": (
                    "item_type",
                    "source_type",
                    "tracking_type",
                    "unit_of_measure",
                )
            },
        ),
        ("Flags", {"fields": ("is_sellable", "is_purchasable", "is_consumable")}),
        ("Pricing", {"fields": ("default_cost", "default_price")}),
        (
            "Reorder",
            {
                "fields": ("reorder_enabled", "reorder_threshold", "reorder_quantity"),
                "classes": ("collapse",),
            },
        ),
        (
            "Bundle Items",
            {
                "fields": ("bundle_items",),
                "classes": ("collapse",),
            },
        ),
        ("Notes", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    filter_horizontal = ("bundle_items",)

    def get_queryset(self, request):
        return (
            super().get_queryset(request).select_related("category", "unit_of_measure")
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        org = getattr(request, "organization", None)
        if org:
            if db_field.name == "category":
                kwargs["queryset"] = ProductCategory.unscoped_objects.filter(
                    organization=org, is_active=True
                )
            elif db_field.name == "unit_of_measure":
                kwargs["queryset"] = UnitOfMeasure.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        org = getattr(request, "organization", None)
        if org and db_field.name == "bundle_items":
            kwargs["queryset"] = Product.unscoped_objects.filter(
                organization=org, status=Product.Status.ACTIVE
            )
        return super().formfield_for_manytomany(db_field, request, **kwargs)


# =============================================================
# SERVICE
# =============================================================


class ChecklistTemplateInline(admin.TabularInline):
    model = ChecklistTemplate
    extra = 0
    fields = ("name", "version", "is_active")
    show_change_link = True
    readonly_fields = ("version",)


@admin.register(Service, site=flowlynk_admin_site)
class ServiceAdmin(ImportCSVMixin, TenantScopedAdmin):
    # Import
    import_url_name = "service-import"
    import_button_label = "Import Services CSV"
    import_page_title = "Import Services"
    change_list_template = "admin/import_changelist.html"

    def get_importer(self, organization, membership=None):
        from apps.crm.catalog.services import ServiceImporter

        return ServiceImporter(organization=organization, membership=membership)

    # Standard config
    list_display = (
        "name",
        "code",
        "category",
        "status",
        "base_rate",
        "base_fee",
        "base_duration_minutes",
        "default_recurrence",
    )
    list_filter = ("status", "default_recurrence", "travel_surcharge", "category")
    search_fields = ("name", "code", "description")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ChecklistTemplateInline]

    fieldsets = (
        (None, {"fields": ("code", "name", "category", "description", "status")}),
        (
            "Operations",
            {"fields": ("base_duration_minutes", "skill_tags", "unit_of_measure")},
        ),
        ("Recurrence", {"fields": ("default_recurrence", "recurrence_options")}),
        (
            "Pricing",
            {"fields": ("base_rate", "base_fee", "min_charge", "travel_surcharge")},
        ),
        (
            "Relationships",
            {
                "fields": ("allowed_addons", "required_products"),
                "classes": ("collapse",),
            },
        ),
        ("Notes", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    filter_horizontal = ("allowed_addons", "required_products")

    def get_queryset(self, request):
        return (
            super().get_queryset(request).select_related("category", "unit_of_measure")
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        org = getattr(request, "organization", None)
        if org:
            if db_field.name == "category":
                kwargs["queryset"] = ServiceCategory.unscoped_objects.filter(
                    organization=org, is_active=True
                )
            elif db_field.name == "unit_of_measure":
                kwargs["queryset"] = UnitOfMeasure.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        org = getattr(request, "organization", None)
        if org:
            if db_field.name == "allowed_addons":
                kwargs["queryset"] = Service.unscoped_objects.filter(
                    organization=org, status=Service.Status.ACTIVE
                )
            elif db_field.name == "required_products":
                kwargs["queryset"] = Product.unscoped_objects.filter(
                    organization=org, status=Product.Status.ACTIVE
                )
        return super().formfield_for_manytomany(db_field, request, **kwargs)


# =============================================================
# CHECKLIST
# =============================================================


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 3
    fields = ("order", "description", "is_required")


@admin.register(ChecklistTemplate, site=flowlynk_admin_site)
class ChecklistTemplateAdmin(TenantScopedAdmin):
    list_display = ("name", "service", "version", "is_active", "get_item_count")
    list_filter = ("is_active",)
    search_fields = ("name", "service__name", "service__code")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ChecklistItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("service")

    @admin.display(description="Steps")
    def get_item_count(self, obj):
        return obj.items.count()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "service":
            org = getattr(request, "organization", None)
            if org:
                kwargs["queryset"] = Service.unscoped_objects.filter(
                    organization=org, status=Service.Status.ACTIVE
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# =============================================================
# MATERIAL
# =============================================================


@admin.register(Material, site=flowlynk_admin_site)
class MaterialAdmin(TenantScopedAdmin):
    list_display = (
        "sku",
        "name",
        "unit_of_measure",
        "tracking_type",
        "status",
        "unit_cost",
    )
    list_filter = ("status", "tracking_type", "is_purchasable", "is_consumable")
    search_fields = ("name", "sku", "barcode")
    readonly_fields = ("created_at", "updated_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "unit_of_measure":
            org = getattr(request, "organization", None)
            if org:
                kwargs["queryset"] = UnitOfMeasure.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
