from django import template
from django.db.models import Count, Sum
from django.utils import timezone

register = template.Library()


@register.simple_tag(takes_context=True)
def staff_billing(context):
    """This month's bills from the Billing screen, per staff member who did the work."""
    company = getattr(context.get("request"), "company", None)
    if company is None:
        return []
    from apps.sales.models import SalesInvoice
    first = timezone.localdate().replace(day=1)
    return list(SalesInvoice.objects.for_company(company).filter(served_by__isnull=False, date__gte=first)
                .exclude(status="void").values("served_by__name")
                .annotate(bills=Count("id"), total=Sum("total")).order_by("-total"))
