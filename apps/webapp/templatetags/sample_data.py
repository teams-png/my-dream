from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def sample_summary(context):
    """What the sample kit added for the active business, or None when there is nothing to remove."""
    request = context.get("request")
    company = getattr(request, "company", None)
    if company is None:
        return None
    from apps.industry import sample_kit
    if not sample_kit.applies(company):
        return None
    found = sample_kit.summary(company)
    found["loaded"] = bool(found["total"])
    return found


@register.simple_tag(takes_context=True)
def setup_checklist(context):
    request = context.get("request")
    company = getattr(request, "company", None)
    if company is None:
        return None
    from apps.webapp.checklist import summary
    return summary(company)
