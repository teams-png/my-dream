"""Who to remind today, per type of business, with a ready WhatsApp message.

  revisit    – customers whose last bill was N days ago (salon haircut, car wash, pharmacy refill, any shop)
  membership – gym members whose membership ends within a few days or ended last week
A customer reminded in the last 14 days is left out. Sending opens WhatsApp with the message typed in;
the owner presses send, so nothing goes out on their behalf without them seeing it.
"""
import datetime
from urllib.parse import quote

from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.modules.catalog import ALIASES, business_group

QUIET_DAYS = 14
REVISIT_DAYS = {"saloon": 30, "beauty_parlour": 30, "spa": 45, "vehicle_wash": 30, "medical_shop": 30,
                "pet_shop": 30, "protein_shop": 30, "laundry_dry_cleaning": 14, "optical_shop": 365,
                "auto_garage": 120, "ac_maintenance": 180, "dental_clinic": 180, "pest_control": 90}
DEFAULT_REVISIT_DAYS = 45


def _code(company):
    code = company.business_type.code
    return ALIASES.get(code, code)


def revisit_days(company):
    return REVISIT_DAYS.get(_code(company), DEFAULT_REVISIT_DAYS)


def revisit_message(company, customer):
    code, name, shop = _code(company), customer.name.replace(" (sample)", ""), company.name
    texts = {
        "saloon": _("Hi %(name)s, it has been a while since your last visit to %(shop)s. Shall we book your next haircut? Reply with a time that suits you."),
        "beauty_parlour": _("Hi %(name)s, it is time for your next beauty treatment at %(shop)s. Reply with a day that suits you and we will book it."),
        "spa": _("Hi %(name)s, treat yourself again! Reply to book your next relaxing session at %(shop)s."),
        "vehicle_wash": _("Hi %(name)s, your vehicle is due for its wash at %(shop)s. Reply to book a slot."),
        "medical_shop": _("Hi %(name)s, it may be time to refill your medicines from %(shop)s. Reply and we will keep them ready for you."),
        "laundry_dry_cleaning": _("Hi %(name)s, any clothes for washing or dry cleaning? Reply and %(shop)s will arrange a pickup."),
    }
    default = _("Hi %(name)s, we miss you at %(shop)s! Visit us again soon – we have something new for you.")
    return texts.get(code, default) % {"name": name, "shop": shop}


def membership_message(company, member):
    return _("Hi %(name)s, your %(plan)s membership at %(shop)s ends on %(date)s. Renew now to keep training without a break.") % {
        "name": member.customer.name.replace(" (sample)", ""), "plan": member.membership_plan.name, "shop": company.name,
        "date": member.membership_end.strftime("%d %b %Y")}


def whatsapp_link(company, customer, text):
    from apps.sales.sharing import normalise_phone
    number = normalise_phone(customer.phone, company.country)
    return f"https://wa.me/{number}?text={quote(text)}" if number else ""


def _recently_reminded(company, kind):
    from .models import CustomerReminder
    since = timezone.now() - datetime.timedelta(days=QUIET_DAYS)
    return set(CustomerReminder.objects.filter(company=company, kind=kind, sent_at__gte=since)
               .values_list("customer_id", flat=True))


def due(company, days=None, limit=200):
    """[{kind, customer, reason, message, link}] for today."""
    from apps.customers.models import Customer
    from apps.sales.models import SalesInvoice
    from apps.sales.pos import WALK_IN
    today = timezone.localdate()
    rows = []
    if _code(company) == "gym":
        from apps.verticals.gym.models import GymMember
        skip = _recently_reminded(company, "membership")
        members = (GymMember.objects.filter(company=company, membership_end__gte=today - datetime.timedelta(days=7),
                                            membership_end__lte=today + datetime.timedelta(days=3))
                   .exclude(status="frozen").exclude(customer_id__in=skip)
                   .select_related("customer", "membership_plan").order_by("membership_end"))
        for m in members[:limit]:
            left = (m.membership_end - today).days
            reason = _("Membership ends in %(n)s days") % {"n": left} if left >= 0 else \
                _("Membership ended %(n)s days ago") % {"n": -left}
            text = membership_message(company, m)
            rows.append({"kind": "membership", "customer": m.customer, "reason": reason, "message": text,
                         "link": whatsapp_link(company, m.customer, text)})
    days = days or revisit_days(company)
    skip = _recently_reminded(company, "revisit") | {r["customer"].id for r in rows}
    last = (SalesInvoice.objects.for_company(company).exclude(status="void").values("customer_id")
            .annotate(last=Max("date"))
            .filter(last__lte=today - datetime.timedelta(days=days), last__gte=today - datetime.timedelta(days=days * 4)))
    last_by_id = {r["customer_id"]: r["last"] for r in last}
    customers = (Customer.objects.for_company(company).filter(id__in=last_by_id, is_active=True)
                 .exclude(id__in=skip).exclude(name=WALK_IN).exclude(phone=""))
    for c in sorted(customers, key=lambda c: last_by_id[c.id])[:limit]:
        text = revisit_message(company, c)
        rows.append({"kind": "revisit", "customer": c, "message": text, "link": whatsapp_link(company, c, text),
                     "reason": _("Last visit %(n)s days ago") % {"n": (today - last_by_id[c.id]).days}})
    return rows


def applies(company):
    return business_group(_code(company)) != "project"
