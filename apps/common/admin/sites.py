"""
apps.common.admin.sites — Custom AdminSite with Platform / CRM grouping.

Requirement: All apps display under exactly two top-level headings:
  - Platform: apps.platform.*
  - CRM: everything else (apps.crm.*, apps.scheduling.*, apps.common.*)

This override rewrites get_app_list() to group by prefix.

Admin access is granted to:
  - Superusers (is_staff + is_superuser) — always
  - Users with an active membership in the resolved org — Phase 1 admin-first
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

    def has_permission(self, request):
        """
        Grant admin access if the user is:
        1. A Django superuser/staff (standard admin behavior), OR
        2. An authenticated user with an active membership in the
           resolved tenant org (set by TenantMiddleware).

        This is what allows tenant users (who don't have is_staff=True)
        to use the admin in Phase 1. RBAC capabilities control what
        they can see/do once inside — this just gets them through the door.
        """
        user = request.user
        if not user.is_active:
            return False

        # Standard Django admin check
        if user.is_staff:
            return True

        # Phase 1 tenant access: active membership = admin access
        membership = getattr(request, "membership", None)
        if membership is not None and membership.is_active:
            return True

        return False

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
