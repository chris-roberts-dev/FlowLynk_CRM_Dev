"""
apps.crm.catalog.admin — Catalog item and checklist admin.

CatalogItem with filters by type, inline checklist templates, CSV import.
ChecklistTemplate with inline items.
"""

from django.contrib import admin

from apps.common.admin import TenantScopedAdmin, flowlynk_admin_site
from apps.common.admin.import_mixin import ImportCSVMixin
from apps.crm.catalog.models import (
    CatalogItem,
    ChecklistItem,
    ChecklistTemplate,
)


# ──────────────────────────────────────────────
# Inlines
# ──────────────────────────────────────────────
class ChecklistTemplateInline(admin.TabularInline):
    model = ChecklistTemplate
    extra = 0
    fields = ("name", "version", "is_active")
    show_change_link = True
    readonly_fields = ("version",)


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 3
    fields = ("order", "description", "is_required")


# ──────────────────────────────────────────────
# CatalogItem (with CSV import)
# ──────────────────────────────────────────────
@admin.register(CatalogItem, site=flowlynk_admin_site)
class CatalogItemAdmin(ImportCSVMixin, TenantScopedAdmin):
    # Import configuration
    import_url_name = "catalog-import"
    import_button_label = "Import Catalog CSV"
    import_page_title = "Import Catalog Items"
    change_list_template = "admin/import_changelist.html"

    def get_importer(self, organization, membership=None):
        from apps.crm.catalog.services import CatalogImporter

        return CatalogImporter(organization=organization, membership=membership)

    # Standard admin config
    list_display = (
        "name",
        "code",
        "item_type",
        "base_rate",
        "base_fee",
        "base_duration_minutes",
        "default_recurrence",
        "is_active",
    )
    list_filter = ("item_type", "is_active", "default_recurrence", "travel_surcharge")
    search_fields = ("name", "code", "description")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ChecklistTemplateInline]

    fieldsets = (
        (None, {"fields": ("code", "name", "item_type", "description", "is_active")}),
        (
            "Operations",
            {
                "fields": (
                    "base_duration_minutes",
                    "skill_tags",
                    "default_recurrence",
                    "recurrence_options",
                )
            },
        ),
        (
            "Pricing",
            {"fields": ("base_rate", "base_fee", "min_charge", "travel_surcharge")},
        ),
        (
            "Relationships",
            {
                "fields": ("allowed_addons", "bundle_items"),
                "classes": ("collapse",),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    filter_horizontal = ("allowed_addons", "bundle_items")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("allowed_addons", "bundle_items")

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Limit M2M choices to current org's items."""
        org = getattr(request, "organization", None)
        if org is not None:
            if db_field.name == "allowed_addons":
                from apps.crm.catalog.models import ItemType

                kwargs["queryset"] = CatalogItem.unscoped_objects.filter(
                    organization=org, item_type=ItemType.ADD_ON, is_active=True
                )
            elif db_field.name == "bundle_items":
                kwargs["queryset"] = CatalogItem.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_manytomany(db_field, request, **kwargs)


# ──────────────────────────────────────────────
# ChecklistTemplate
# ──────────────────────────────────────────────
@admin.register(ChecklistTemplate, site=flowlynk_admin_site)
class ChecklistTemplateAdmin(TenantScopedAdmin):
    list_display = ("name", "catalog_item", "version", "is_active", "get_item_count")
    list_filter = ("is_active", "catalog_item__item_type")
    search_fields = ("name", "catalog_item__name", "catalog_item__code")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ChecklistItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("catalog_item")

    @admin.display(description="Steps")
    def get_item_count(self, obj):
        return obj.items.count()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit catalog_item to current org."""
        if db_field.name == "catalog_item":
            org = getattr(request, "organization", None)
            if org is not None:
                kwargs["queryset"] = CatalogItem.unscoped_objects.filter(
                    organization=org, is_active=True
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
