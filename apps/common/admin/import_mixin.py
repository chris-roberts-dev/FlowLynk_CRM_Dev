"""
apps.common.admin.import_mixin — Reusable CSV import for Django admin.

Adds an "Import CSV" button to any ModelAdmin changelist. Clicking it
opens an upload form. The workflow is:

1. Upload CSV → runs dry-run → shows preview (created/updated/unchanged/errors)
2. If no errors, shows a "Confirm Import" button → commits changes
3. Results page shows final counts

Usage:
    class CatalogItemAdmin(ImportCSVMixin, TenantScopedAdmin):
        import_url_name = "catalog-import"
        import_template = "admin/csv_import.html"  # shared template

        def get_importer(self, organization, membership=None):
            return CatalogImporter(organization=organization, membership=membership)
"""

import logging

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse

logger = logging.getLogger(__name__)


class ImportCSVMixin:
    """
    Mixin that adds CSV import functionality to a ModelAdmin.

    Subclasses must define:
        import_url_name: str — unique URL name for the import view
        get_importer(organization, membership) — returns a BaseImporter instance

    Optional:
        import_template: str — template path (default: "admin/csv_import.html")
    """

    import_url_name = None  # Must be set by subclass
    import_template = "admin/csv_import.html"

    def get_importer(self, organization, membership=None):
        """Return an importer instance. Override in subclass."""
        raise NotImplementedError("Subclass must implement get_importer()")

    def get_urls(self):
        """Add the import URL to the admin's URL patterns."""
        custom_urls = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name=self.import_url_name,
            ),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        """Add import URL to the changelist context for the button."""
        extra_context = extra_context or {}
        extra_context["import_url"] = reverse(f"flowlynk_admin:{self.import_url_name}")
        extra_context["import_label"] = getattr(
            self, "import_button_label", "Import CSV"
        )
        return super().changelist_view(request, extra_context=extra_context)

    def import_csv_view(self, request):
        """Handle the CSV import upload, dry-run, and commit."""
        org = getattr(request, "organization", None)
        membership = getattr(request, "membership", None)

        context = {
            **self.admin_site.each_context(request),
            "title": getattr(self, "import_page_title", "Import CSV"),
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
        }

        if request.method == "POST":
            action = request.POST.get("action", "dry_run")
            csv_file = request.FILES.get("csv_file")

            # Commit action — uses CSV content stored in session from dry-run
            if action == "commit":
                csv_content = request.session.pop("_import_csv_content", None)
                file_name = request.session.pop("_import_csv_filename", "")

                if not csv_content:
                    messages.error(
                        request, "Import session expired. Please upload the file again."
                    )
                    return render(request, self.import_template, context)

                if org is None:
                    messages.error(
                        request,
                        "No organization context. Are you on a tenant subdomain?",
                    )
                    return render(request, self.import_template, context)

                importer = self.get_importer(org, membership)
                result = importer.run(csv_content, dry_run=False, file_name=file_name)

                context["result"] = result
                context["committed"] = True

                if result.has_errors:
                    messages.error(
                        request, f"Import failed with {len(result.errors)} error(s)."
                    )
                else:
                    messages.success(
                        request,
                        f"Import complete: {len(result.created)} created, "
                        f"{len(result.updated)} updated, "
                        f"{len(result.unchanged)} unchanged.",
                    )
                return render(request, self.import_template, context)

            # Dry-run action — upload and preview
            if not csv_file:
                messages.error(request, "Please select a CSV file to upload.")
                return render(request, self.import_template, context)

            try:
                csv_content = csv_file.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                messages.error(
                    request, "File encoding error. Please upload a UTF-8 CSV file."
                )
                return render(request, self.import_template, context)

            file_name = csv_file.name

            if org is None:
                messages.error(
                    request, "No organization context. Are you on a tenant subdomain?"
                )
                return render(request, self.import_template, context)

            importer = self.get_importer(org, membership)
            result = importer.run(csv_content, dry_run=True, file_name=file_name)

            context["result"] = result
            context["dry_run"] = True
            context["file_name"] = file_name

            if not result.has_errors:
                # Store CSV in session so commit doesn't require re-upload
                request.session["_import_csv_content"] = csv_content
                request.session["_import_csv_filename"] = file_name

            return render(request, self.import_template, context)

        # GET — show upload form
        return render(request, self.import_template, context)
