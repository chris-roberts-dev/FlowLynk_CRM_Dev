"""
FlowLynk — Root URL configuration.

Admin is served via custom AdminSite (Platform/CRM grouping).
Public landing page served at root (base domain).
Auth views served at /auth/ (base domain).
"""

from django.urls import include, path

from apps.common.admin.sites import flowlynk_admin_site
from apps.platform.organizations.views import LandingPageView

flowlynk_admin_site.site_header = "FlowLynk Administration"
flowlynk_admin_site.site_title = "FlowLynk"
flowlynk_admin_site.index_title = "Dashboard"

urlpatterns = [
    # Public landing page (base domain) — handles ?error= from TenantMiddleware
    path("", LandingPageView.as_view(), name="landing"),
    # Authentication (base domain)
    path("auth/", include("apps.platform.accounts.urls")),
    # Custom admin site with Platform / CRM grouping
    path("admin/", flowlynk_admin_site.urls),
]
