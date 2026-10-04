from django.shortcuts import redirect
from django.urls import reverse


class ActiveCompanyMiddleware:
    """
    Resolves request.company and request.role from the authenticated user's
    session-selected CompanyMembership.

    Critical rule (Phase 0 Section 3 / Phase 1 Section 2): the active company
    is NEVER taken from a client-supplied id in the URL, query string, or
    request body — only from request.session['active_company_id'], which is
    itself only ever set by the company-switcher view after verifying the
    user has an active CompanyMembership for that company.

    BUGFIX (found while writing the Phase 20 test suite): this is a plain
    Django middleware, which runs BEFORE DRF's authentication classes ever
    see the request (DRF authenticates lazily, inside APIView.dispatch,
    which happens after all middleware has already run). Since the API
    uses JWTAuthentication (config/settings/base.py REST_FRAMEWORK), a
    request carrying only an `Authorization: Bearer <token>` header — no
    session cookie — reached this point with `request.user` still
    AnonymousUser, so `request.company` was silently left None for every
    JWT-authenticated API call, and every HasCompanyPermission check failed.
    Fix: if session auth didn't already populate an authenticated user, try
    JWTAuthentication explicitly, right here, before resolving membership.
    """

    EXEMPT_PATH_PREFIXES = ("/admin", "/api/accounts/", "/static", "/media")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company = None
        request.role = None
        request.membership = None

        if request.path.startswith(self.EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        if not request.user.is_authenticated:
            self._authenticate_via_jwt(request)

        if request.user.is_authenticated:
            company_id = request.session.get("active_company_id")
            membership = None

            if company_id:
                membership = (
                    request.user.memberships
                    .select_related("company", "role")
                    .filter(company_id=company_id, is_active=True, company__is_active=True)
                    .first()
                )

            if membership is None:
                # fall back to the user's first active membership and persist it as the choice
                membership = (
                    request.user.memberships
                    .select_related("company", "role")
                    .filter(is_active=True, company__is_active=True)
                    .first()
                )
                if membership:
                    request.session["active_company_id"] = membership.company_id

            if membership:
                request.company = membership.company
                request.role = membership.role
                request.membership = membership

        from apps.common import form_hints
        from apps.inventory import branch_access
        token = branch_access.activate(branch_access.ids_for(request.membership))
        hints_token = form_hints.activate(request.company)
        request.branch_ids = branch_access.allowed()
        try:
            return self.get_response(request)
        finally:
            form_hints.reset(hints_token)
            branch_access.reset(token)

    def _authenticate_via_jwt(self, request):
        """Best-effort: silently no-ops for anonymous/session/cookie-only requests."""
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

        try:
            result = JWTAuthentication().authenticate(request)
        except (InvalidToken, TokenError):
            return
        if result is not None:
            request.user, _ = result
