"""
apps.common.admin.sites — Custom AdminSite with Platform / CRM grouping.

Requirement: All apps display under exactly two top-level headings:
  - Platform: apps.platform.*
  - CRM: everything else (apps.crm.*, apps.scheduling.*, apps.common.*)

This override rewrites get_app_list() to group by prefix.
"""
from django.contrib.admin import AdminSite


class FlowLynkAdminSite(AdminSite):
    site_header = "FlowLynk Administration"
    site_title = "FlowLynk"
    index_title = "Dashboard"

    # ── Mapping: AppConfig.name prefix → admin group heading ──
    GROUP_MAP = {
        "apps.platform.": "Platform",
    }
    DEFAULT_GROUP = "CRM"

    def _get_group(self, app_name: str) -> str:
        """Resolve the admin group heading for a given app name."""
        for prefix, group in self.GROUP_MAP.items():
            if app_name.startswith(prefix):
                return group
        return self.DEFAULT_GROUP

    def get_app_list(self, request, app_label=None):
        """
        Override to merge all apps into two super-groups: Platform and CRM.

        Each super-group is a dict that looks like a normal app_list entry
        but with models aggregated from multiple Django apps.
        """
        original = super().get_app_list(request, app_label=app_label)

        groups: dict[str, dict] = {}
        # Ensure stable ordering: Platform first, CRM second
        for heading in ("Platform", "CRM"):
            groups[heading] = {
                "name": heading,
                "app_label": heading.lower(),
                "app_url": "",
                "has_module_perms": True,
                "models": [],
            }

        for app_dict in original:
            app_name = app_dict.get("app_label", "")
            # Resolve the dotted app name from registry for accurate prefix matching
            from django.apps import apps as app_registry

            try:
                config = app_registry.get_app_config(app_name)
                dotted_name = config.name
            except LookupError:
                dotted_name = app_name

            heading = self._get_group(dotted_name)
            groups[heading]["models"].extend(app_dict.get("models", []))

        # Sort models alphabetically within each group
        for group in groups.values():
            group["models"].sort(key=lambda m: m["name"])

        # Return only groups that have visible models
        return [g for g in groups.values() if g["models"]]


# Singleton instance used in urls.py
flowlynk_admin_site = FlowLynkAdminSite(name="flowlynk_admin")
