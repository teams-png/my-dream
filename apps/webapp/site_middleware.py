"""Serves a business's hosted website when the request comes in on that business's own domain."""
from apps.industry import site_builder


class CustomDomainMiddleware:
    """Runs first. A request whose Host is a live client domain gets only the public website routes
    (apps.webapp.site_urls) — never the login or dashboard. Other hosts go through untouched."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = (request.META.get("HTTP_HOST") or "").split(":")[0].strip().lower()
        design = site_builder.design_for_host(host) if host else None
        if design is not None:
            request.site_design = design
            request.urlconf = "apps.webapp.site_urls"
            # The domain is checked against our own list above, so skip ALLOWED_HOSTS for it.
            request.get_host = lambda: request.META["HTTP_HOST"]
        return self.get_response(request)
