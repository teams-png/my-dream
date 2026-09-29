def active_company(request):
    """Exposes request.company / request.role to templates as {{ active_company }} / {{ active_role }}."""
    company = getattr(request, "company", None)
    from apps.modules.catalog import business_group
    return {
        "active_company": company,
        "active_role": getattr(request, "role", None),
        "active_business_group": business_group(company.business_type.code) if company else None,
    }
