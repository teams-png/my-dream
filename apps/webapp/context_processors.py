def user_companies(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"my_companies": []}
    memberships = (
        request.user.memberships
        .select_related("company", "company__business_type")
        .filter(is_active=True, company__is_active=True)
        .order_by("company__name")
    )
    return {"my_companies": [m.company for m in memberships]}


def enabled_features(request):
    """Exposes which toggleable webapp features (POS, Coupons, Branches, ...)
    a platform admin has left enabled for the active company, so base.html
    can hide nav links for anything disabled. A company with no rows at all
    for a feature is treated as enabled (default-on, e.g. companies created
    before this toggle existed)."""
    company = getattr(request, "company", None)
    if company is None:
        return {"enabled_features": set()}
    from apps.modules.models import CompanyModule
    disabled = set(
        CompanyModule.objects.filter(company=company, is_active=False).values_list("module__code", flat=True)
    )
    all_codes = {"webui_pos", "webui_returns_refunds", "webui_coupons_loyalty", "webui_expenses",
                 "webui_suppliers_purchases", "webui_branches", "webui_team_roles", "webui_analytics"}
    return {"enabled_features": all_codes - disabled}


def active_business_profile(request):
    """Industry terminology for navigation and generic suite screens."""
    company = getattr(request, "company", None)
    if company is None or not getattr(company, "business_type_id", None):
        return {"active_business_profile": {}}
    from apps.modules.catalog import business_profile
    return {"active_business_profile": business_profile(company.business_type.code)}


def form_samples(request):
    """Examples for hand-written forms (static/js/form-hints.js); Django forms get them server-side."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from apps.common import form_hints
    return {"bp_form_samples": form_hints.client_samples()}
