from django.http import JsonResponse
from django.shortcuts import redirect

# Routes an expired-subscription company can still reach (Owner/billing only — Phase 0 Section 7).
ALLOWED_PATH_PREFIXES = (
    "/admin", "/api/accounts/", "/api/subscriptions/", "/static", "/media",
)

# Webapp (HTML) paths an expired company must still reach: billing itself, auth, and the platform admin portal.
WEBAPP_ALLOWED_PREFIXES = (
    "/billing", "/login", "/logout", "/password-reset", "/reset/", "/platform", "/admin-console",
)


class SubscriptionGuardMiddleware:
    """
    Once a subscription's end_date has passed, blocks non-billing routes and
    redirects to a "renew your subscription" response — a middleware check,
    not scattered permission checks (Phase 0 Section 7).
    Must run AFTER ActiveCompanyMiddleware (see settings/base.py ordering).

    Checks the date directly rather than only trusting Subscription.status,
    since that field is normally flipped by a daily Celery beat task
    (run_daily_expiry_check) that may not be running in every environment —
    a date comparison is correct even with no scheduler at all.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        company = getattr(request, "company", None)

        if company is not None and request.path.startswith("/api/") \
                and not request.path.startswith(ALLOWED_PATH_PREFIXES):
            subscription = getattr(company, "subscription", None)
            is_owner = getattr(request, "role", None) and request.role.name == "Owner"

            if subscription and not self._is_usable(subscription) and not is_owner:
                return JsonResponse(
                    {"detail": "Your subscription has expired. Please renew to continue."},
                    status=402,
                )

        if company is not None and not request.path.startswith("/api/") \
                and not request.path.startswith(WEBAPP_ALLOWED_PREFIXES) \
                and not getattr(request.user, "is_superuser", False):
            subscription = getattr(company, "subscription", None)
            if subscription and not self._is_usable(subscription):
                return redirect("webapp:billing")

        return self.get_response(request)

    @staticmethod
    def _is_usable(subscription):
        """
        Checks BOTH the date and the status field. The date check alone
        (this method's original form) misses a subscription that's been
        explicitly marked "expired"/"cancelled" (e.g. by an admin action,
        a payment-webhook handler, or a test) while `end_date` is still in
        the future — that row would otherwise keep granting access. The
        date check stays as a fallback for the case the docstring above
        already covers (status not yet flipped by the daily Celery task).
        """
        from django.utils import timezone

        if subscription.status in ("expired", "cancelled"):
            return False
        today = timezone.localdate()
        return subscription.end_date >= today or bool(subscription.grace_ends_at and subscription.grace_ends_at >= today)
