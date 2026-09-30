"""Opens an industry module only for the business types it belongs to."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.modules.catalog import business_features


def company_features(company):
    if company is None:
        return set()
    features = business_features(company.business_type.code)
    for code in company.business_suites.filter(is_active=True).values_list("business_type__code", flat=True):
        features |= business_features(code)
    return features


def require_industry(feature):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            company = getattr(request, "company", None)
            if company is None:
                return render(request, "webapp/no_company.html")
            if feature not in company_features(company):
                messages.error(request, _("This module isn't part of your business type."))
                return redirect("webapp:dashboard")
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
