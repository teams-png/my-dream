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


BOOK_URL = {"saloon": "webapp:saloon_appointment_book", "barber_shop": "webapp:saloon_appointment_book",
            "spa": "webapp:appointment_book", "beauty_parlour": "webapp:beauty_appointment_book",
            "beauty_salon": "webapp:beauty_appointment_book", "vehicle_wash": "webapp:wash_order_book",
            "car_wash": "webapp:wash_order_book"}


@register.simple_tag(takes_context=True)
def quick_actions(context):
    """The big buttons at the top of the overview: new bill, and new booking where the business takes bookings."""
    from django.urls import reverse
    from django.utils.translation import gettext as _
    from apps.modules.catalog import business_features, business_group
    request = context.get("request")
    company = getattr(request, "company", None)
    if company is None:
        return []
    code = company.business_type.code
    if business_group(code) == "restaurant":
        return []
    actions = [("🧾", _("New bill"), reverse("webapp:pos"), True)]
    if code in BOOK_URL:
        actions.append(("📅", _("Book appointment"), reverse(BOOK_URL[code]), False))
    elif "bookings" in business_features(code):
        actions.append(("📅", _("New booking"), reverse("webapp:booking_add"), False))
    actions.append(("💬", _("Customer reminders"), reverse("webapp:reminders"), False))
    return actions
