"""Ctrl+K search: one box on every page that finds people, documents and products by name, number or phone.

Pages of the menu are found in the browser from the sidebar itself (so a member only ever sees pages their role
may open); this view adds the business's records."""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import gettext as _

from .industry_access import company_features
from .role_access import can_open

PER_GROUP = 5


def _customers(company, q):
    from apps.customers.models import Customer
    rows = Customer.objects.for_company(company).filter(Q(name__icontains=q) | Q(phone__icontains=q)).order_by("name")
    return [(c.name, c.phone, reverse("webapp:customer_account", args=[c.id])) for c in rows[:PER_GROUP]]


def _invoices(company, q):
    from apps.sales.models import SalesInvoice
    rows = (SalesInvoice.objects.for_company(company).select_related("customer")
            .filter(Q(invoice_number__icontains=q) | Q(customer__name__icontains=q)).order_by("-date", "-id"))
    return [(i.invoice_number, f"{i.customer.name} · {i.date:%d %b %Y} · {i.total}",
             reverse("webapp:invoice_pdf", args=[i.id])) for i in rows[:PER_GROUP]]


def _products(company, q):
    from apps.inventory.models import Product
    rows = (Product.objects.for_company(company).filter(is_active=True)
            .filter(Q(name__icontains=q) | Q(sku__icontains=q)).order_by("name"))
    return [(p.name, f"{p.sku} · {p.selling_price}", reverse("webapp:product_edit", args=[p.id]))
            for p in rows[:PER_GROUP]]


def _suppliers(company, q):
    from apps.suppliers.models import Supplier
    rows = Supplier.objects.for_company(company).filter(Q(name__icontains=q) | Q(phone__icontains=q)).order_by("name")
    return [(s.name, s.phone, reverse("webapp:supplier_detail", args=[s.id])) for s in rows[:PER_GROUP]]


def _staff(company, q):
    from apps.employees.models import Employee
    rows = (Employee.objects.for_company(company)
            .filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(role_title__icontains=q)).order_by("-is_active", "name"))
    return [(e.name, e.role_title or e.phone, reverse("webapp:staff_detail", args=[e.id])) for e in rows[:PER_GROUP]]


def _candidates(company, q):
    from apps.industry.models import Candidate
    rows = (Candidate.objects.for_company(company)
            .filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(passport_no__icontains=q)
                    | Q(trade__icontains=q)).order_by("name"))
    return [(c.name, " · ".join(x for x in (c.trade, c.passport_no) if x),
             reverse("webapp:rec_candidate_detail", args=[c.id])) for c in rows[:PER_GROUP]]


# (group label, finder, url name the member must be allowed to open, industry feature needed)
GROUPS = [
    ("Customers", _customers, "customer_account", None),
    ("Invoices", _invoices, "invoice_pdf", None),
    ("Products", _products, "product_edit", None),
    ("Candidates", _candidates, "rec_candidate_detail", "recruitment"),
    ("Staff", _staff, "staff_detail", None),
    ("Suppliers", _suppliers, "supplier_detail", None),
]


@login_required
def palette_search(request):
    company = getattr(request, "company", None)
    q = (request.GET.get("q") or "").strip()[:60]
    if company is None or len(q) < 2:
        return JsonResponse({"results": []})
    features = company_features(company)
    results = []
    for label, finder, url_name, feature in GROUPS:
        if (feature and feature not in features) or not can_open(request, url_name):
            continue
        for title, sub, url in finder(company, q):
            results.append({"group": _(label), "title": title, "sub": sub or "", "url": url})
    return JsonResponse({"results": results})
