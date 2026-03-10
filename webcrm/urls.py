"""
FlowLynk — Root URL configuration.

Admin is served via custom AdminSite (Platform/CRM grouping).
Public landing page served at root.
Auth views will be added in EPIC 2.
"""

from django.urls import path
from django.views.generic import TemplateView

from apps.common.admin.sites import flowlynk_admin_site

urlpatterns = [
    # Public landing page
    path(
        "", TemplateView.as_view(template_name="platform/landing.html"), name="landing"
    ),
    # Custom admin site with Platform / CRM grouping
    path("admin/", flowlynk_admin_site.urls),
    # Auth views — added in EPIC 2
    # path("auth/", include("apps.platform.accounts.urls")),
]
