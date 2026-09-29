from .models import BusinessTypeDefaultModule, CompanyModule
from django.core.exceptions import ValidationError
from django.db import transaction


def activate_default_modules(company):
    """
    Called once at company creation (tenants.services.create_company_with_owner).
    Turns 'which features does this business see' into data, not code branches
    (Phase 0 Section 8) — no `if business_type == 'gym':` anywhere in the app layer.
    """
    defaults = BusinessTypeDefaultModule.objects.filter(
        business_type=company.business_type
    ).select_related("module")

    plan_modules = None
    if hasattr(company, "subscription"):
        plan_modules = set(company.subscription.plan.modules.values_list("id", flat=True))
    CompanyModule.objects.bulk_create(
        [CompanyModule(company=company, module=d.module, is_active=(plan_modules is None or d.module_id in plan_modules)) for d in defaults],
        ignore_conflicts=True,
    )


def module_is_enabled(company, code):
    module = company.active_modules().filter(code=code).first()
    if module is None:
        return False
    subscription = getattr(company, "subscription", None)
    if module.is_core or subscription is None:
        return True
    plan_codes = set(subscription.plan.modules.values_list("code", flat=True))
    return not plan_codes or code in plan_codes


@transaction.atomic
def set_company_modules(*, company, module_codes):
    """Platform-admin operation; preserves data and only changes access."""
    from .models import Module
    requested = set(module_codes)
    modules = list(Module.objects.filter(code__in=requested))
    unknown = requested - {m.code for m in modules}
    if unknown:
        raise ValidationError(f"Unknown module codes: {', '.join(sorted(unknown))}")
    subscription = getattr(company, "subscription", None)
    plan_codes = set(subscription.plan.modules.values_list("code", flat=True)) if subscription else set()
    disallowed = {m.code for m in modules if not m.is_core and plan_codes and m.code not in plan_codes}
    if disallowed:
        raise ValidationError(f"Modules not included in the assigned plan: {', '.join(sorted(disallowed))}")
    for module in Module.objects.all():
        enabled = module.is_core or module.code in requested
        CompanyModule.objects.update_or_create(company=company, module=module, defaults={"is_active": enabled})
    return company.active_modules()
