"""
apps.platform.accounts.urls — Authentication URL routes.

All served on the base domain:
    /auth/login/              → LoginView
    /auth/select-org/         → OrgPickerView
    /auth/select-org/<slug>/  → SelectOrgView
    /auth/logout/             → LogoutView
"""
from django.urls import path

from apps.platform.accounts.views import (
    LoginView,
    LogoutView,
    OrgPickerView,
    SelectOrgView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("select-org/", OrgPickerView.as_view(), name="org-picker"),
    path("select-org/<slug:org_slug>/", SelectOrgView.as_view(), name="select-org"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
