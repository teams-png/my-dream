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


# Shortcuts on the Billing / POS top bar, so the counter can jump to the pages it uses most and back.
POS_SHORTCUTS = {
    "saloon": [("📅", "Appointments", "webapp:saloon_appointment_list"), ("✂️", "Services", "webapp:saloon_service_list"),
               ("📊", "Reports", "webapp:saloon_reports")],
    "spa": [("📅", "Appointments", "webapp:appointment_list"), ("💆", "Services", "webapp:spa_service_list"),
            ("📊", "Reports", "webapp:spa_reports")],
    "beauty_parlour": [("📅", "Appointments", "webapp:beauty_appointment_list"),
                       ("💄", "Services", "webapp:beauty_service_list"), ("📊", "Reports", "webapp:beauty_reports")],
    "vehicle_wash": [("🚗", "Orders", "webapp:wash_order_list"), ("🧽", "Packages", "webapp:wash_package_list"),
                     ("📊", "Reports", "webapp:vehicle_wash_reports")],
    "gym": [("🧑", "Members", "webapp:member_list"), ("✅", "Attendance", "webapp:attendance_today"),
            ("📊", "Reports", "webapp:gym_reports")],
}
POS_SHORTCUTS.update(barber_shop=POS_SHORTCUTS["saloon"], beauty_salon=POS_SHORTCUTS["beauty_parlour"],
                     car_wash=POS_SHORTCUTS["vehicle_wash"], fitness_center=POS_SHORTCUTS["gym"])


@register.simple_tag(takes_context=True)
def pos_shortcuts(context):
    """[(icon, label, url)]: Overview first, then the business type's main pages (products and customers otherwise)."""
    from django.urls import reverse
    from django.utils.translation import gettext as _
    request = context.get("request")
    company = getattr(request, "company", None)
    code = company.business_type.code if company else ""
    links = [("🏠", "Overview", "webapp:dashboard")] + POS_SHORTCUTS.get(
        code, [("📦", "Products", "webapp:product_list"), ("👥", "Customers", "webapp:customer_list")])
    return [(icon, _(label), reverse(name)) for icon, label, name in links]


@register.simple_tag(takes_context=True)
def product_picture(context, product):
    """Photo or default picture URL for a product (for lists and the website)."""
    from apps.inventory.pictures import picture_url
    company = getattr(context.get("request"), "company", None)
    return picture_url(product, company.business_type.code if company else "")
