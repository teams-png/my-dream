"""Redirect to a "next" URL only when it stays on this site (no open redirects to other websites)."""
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, fallback, field="next"):
    target = (request.POST.get(field) or request.GET.get(field) or "").strip()
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                 require_https=request.is_secure()):
        return target
    return resolve_url(fallback)
