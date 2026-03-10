"""
apps.platform.accounts.views — Authentication views.

All auth views are served on the base domain (lvh.me / flowlynk.com).

Login flow:
    1. User submits email + password at /auth/login/
    2. On success, resolve active memberships:
       - 0 memberships (non-superuser) → error message
       - 0 memberships (superuser) → redirect to base domain /admin/
       - 1 membership → redirect directly to org subdomain /admin/
       - 2+ memberships → redirect to /auth/select-org/
    3. Org picker shows active orgs, user picks one → redirect to subdomain

Logout:
    - Clears session
    - Redirects to base domain landing page
"""
import logging

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views import View

from apps.platform.accounts.forms import LoginForm
from apps.platform.accounts.models import Membership, MembershipStatus
from apps.platform.accounts.services import (
    build_base_url,
    build_org_admin_url,
    get_active_memberships,
    record_login,
)

logger = logging.getLogger(__name__)


class LoginView(View):
    """Email/password login on the base domain."""

    template_name = "platform/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return self._resolve_memberships(request, request.user)

        form = LoginForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = LoginForm(data=request.POST, request=request)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        user = form.get_user()
        login(request, user)

        logger.info(
            "User '%s' authenticated successfully",
            user.email,
            extra={"user_id": user.pk},
        )

        return self._resolve_memberships(request, user)

    @staticmethod
    def _resolve_memberships(request, user):
        """
        After authentication, decide where to send the user based on
        their active memberships.
        """
        memberships = list(get_active_memberships(user))

        # Superuser with no memberships → base domain admin
        if user.is_superuser and len(memberships) == 0:
            return redirect("/admin/")

        # No memberships → error
        if len(memberships) == 0:
            logout(request)
            logger.warning(
                "User '%s' has no active memberships, logged out",
                user.email,
                extra={"user_id": user.pk},
            )
            return redirect("/?error=no_membership")

        # Single membership → direct redirect
        if len(memberships) == 1:
            record_login(memberships[0])
            return redirect(build_org_admin_url(memberships[0].organization.slug))

        # Multiple memberships → org picker
        return redirect("org-picker")


class OrgPickerView(View):
    """
    Org selection for users with multiple active memberships.

    Shows a list of orgs the user belongs to. Clicking one redirects
    to that org's subdomain.
    """

    template_name = "platform/org_picker.html"

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect("login")

        memberships = get_active_memberships(request.user)

        if not memberships.exists():
            return redirect("/?error=no_membership")

        return render(
            request,
            self.template_name,
            {
                "memberships": memberships,
                "user": request.user,
            },
        )


class SelectOrgView(View):
    """
    Handles the org selection: redirects to the chosen org's subdomain.

    URL: /auth/select-org/<slug>/
    """

    def get(self, request, org_slug):
        if not request.user.is_authenticated:
            return redirect("login")

        # Verify the user actually has a membership in this org
        try:
            membership = Membership.objects.select_related("organization").get(
                user=request.user,
                organization__slug=org_slug,
                status=MembershipStatus.ACTIVE,
            )
        except Membership.DoesNotExist:
            logger.warning(
                "User '%s' attempted to select org '%s' without membership",
                request.user.email,
                org_slug,
            )
            return redirect("org-picker")

        record_login(membership)
        return redirect(build_org_admin_url(org_slug))


class LogoutView(View):
    """Logs out and redirects to base domain landing page."""

    def get(self, request):
        if request.user.is_authenticated:
            logger.info(
                "User '%s' logged out",
                request.user.email,
                extra={"user_id": request.user.pk},
            )
        logout(request)
        return redirect(build_base_url())

    # Support POST logout for CSRF-protected forms
    def post(self, request):
        return self.get(request)
