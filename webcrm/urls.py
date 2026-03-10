"""
FlowLynk — Root URL configuration.

Admin is served via custom AdminSite (Platform/CRM grouping).
Public landing and auth views will be added in EPIC 1–2.
"""
from django.contrib import admin
from django.urls import path

from apps.common.admin.sites import flowlynk_admin_site

urlpatterns = [
    # Custom admin site with Platform / CRM grouping
    path("admin/", flowlynk_admin_site.urls),

    # Public landing page — added in EPIC 1
    # path("", include("apps.platform.organizations.urls")),

    # Auth views — added in EPIC 2
    # path("auth/", include("apps.platform.accounts.urls")),
]
