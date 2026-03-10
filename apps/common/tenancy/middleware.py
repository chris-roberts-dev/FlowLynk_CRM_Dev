"""
apps.common.tenancy.middleware — Tenant resolution middleware.

Full implementation in EPIC 1. This stub defines the interface so that
other modules can reference it during scaffold testing.

Resolution strategy (priority order):
1. Subdomain: {org_slug}.lvh.me → lookup Organization by slug
2. Explicit path: /login/{org_slug} (optional)
3. Email discovery: resolve memberships from global login

Sets on request:
- request.organization  (Organization instance or None)
- request.membership    (Membership instance or None)
"""


class TenantMiddleware:
    """
    Placeholder — will be activated in EPIC 1.

    Once active, this middleware:
    - Extracts subdomain from Host header
    - Resolves Organization by slug
    - Sets request.organization and request.membership
    - Redirects to base domain on invalid/suspended org
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # EPIC 1: implement subdomain resolution here
        request.organization = None
        request.membership = None
        return self.get_response(request)
