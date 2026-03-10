"""
apps.platform.organizations.views — Public-facing views.

LandingPageView: serves the base domain landing page and handles
error messages from TenantMiddleware redirects.
"""
from django.views.generic import TemplateView


# Map error codes (from middleware ?error= param) to user-friendly messages.
ERROR_MESSAGES = {
    "invalid_org": (
        "The organization you requested could not be found. "
        "Please check the URL and try again.",
        "warning",
    ),
    "org_suspended": (
        "This organization's account has been suspended. "
        "Please contact your administrator.",
        "danger",
    ),
    "no_membership": (
        "You do not have access to the requested organization. "
        "Please contact your administrator if you believe this is an error.",
        "warning",
    ),
    "login_required": (
        "Please log in to access your organization.",
        "info",
    ),
}


class LandingPageView(TemplateView):
    template_name = "platform/landing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        error_code = self.request.GET.get("error")
        if error_code and error_code in ERROR_MESSAGES:
            message, level = ERROR_MESSAGES[error_code]
            context["error_message"] = message
            context["error_level"] = level

        return context
