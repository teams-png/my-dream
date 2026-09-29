"""First-run setup wizard: business details, first items, devices."""
import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.inventory.models import Product, ProductCategory, Unit, Warehouse
from apps.inventory.services import record_stock_movement
from apps.modules.catalog import business_group
from apps.tenants.models import Company

from .views import require_permission

STEPS = ["business", "catalog", "devices", "done"]
MAX_ROWS = 20
MAX_TABLES = 100


class BusinessStepForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "logo", "address", "phone", "vat_number", "default_currency"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}


def _group(company):
    group = business_group(company.business_type.code)
    return group if group in {"restaurant", "retail", "service", "project"} else "retail"


def _money(raw):
    try:
        value = Decimal(str(raw).strip() or "0").quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return value if value >= 0 else None


def _next_sku(company, prefix):
    n = Product.objects.for_company(company).filter(sku__startswith=prefix).count() + 1
    while Product.objects.for_company(company).filter(sku=f"{prefix}{n:04d}").exists():
        n += 1
    return f"{prefix}{n:04d}"


def read_rows(post):
    """The item rows typed in the wizard, skipping blank ones; returns (rows, errors)."""
    rows, errors = [], []
    names, prices = post.getlist("item_name"), post.getlist("item_price")
    stocks, codes, cats = post.getlist("item_stock"), post.getlist("item_code"), post.getlist("item_category")
    for i, name in enumerate(names[:MAX_ROWS]):
        name = name.strip()[:255]
        if not name:
            continue
        price = _money(prices[i] if i < len(prices) else "")
        stock = _money(stocks[i] if i < len(stocks) else "")
        if price is None or stock is None:
            errors.append(_("Check the price and stock for “%(name)s”.") % {"name": name})
            continue
        rows.append({"name": name, "price": price, "stock": stock,
                     "code": re.sub(r"\s+", "", codes[i] if i < len(codes) else "")[:50],
                     "category": (cats[i] if i < len(cats) else "").strip()[:100]})
    return rows, errors


@transaction.atomic
def add_catalog(company, rows, *, group, tables=0):
    """Creates products (or menu items) and dining tables from the wizard."""
    from apps.verticals.restaurant.models import DiningArea, DiningTable, RestaurantMenuItem

    unit, _created = Unit.objects.get_or_create(company=company, name="piece")
    warehouse = (Warehouse.objects.for_company(company).filter(is_default=True).first()
                 or Warehouse.objects.for_company(company).first()
                 or Warehouse.objects.create(company=company, name="Main", is_default=True))
    categories = {}
    created = 0
    for row in rows:
        category = None
        if row["category"]:
            key = row["category"].lower()
            if key not in categories:
                categories[key] = (ProductCategory.objects.for_company(company).filter(name__iexact=row["category"]).first()
                                   or ProductCategory.objects.create(company=company, name=row["category"]))
            category = categories[key]
        sku = row["code"] or _next_sku(company, "M-" if group == "restaurant" else "P-")
        if Product.objects.for_company(company).filter(sku=sku).exists():
            raise ValueError(_("The code %(code)s is already used by another product.") % {"code": sku})
        stocked = group == "retail"
        product = Product.objects.create(
            company=company, sku=sku, name=row["name"], category=category, unit=unit,
            selling_price=row["price"], is_stock_tracked=stocked, tracking_type="basic" if stocked else "none",
        )
        if group == "restaurant":
            RestaurantMenuItem.objects.create(company=company, product=product)
        if stocked and row["stock"] > 0:
            record_stock_movement(company=company, product=product, warehouse=warehouse,
                                  quantity=row["stock"], reason="adjustment", reference="Opening stock")
        created += 1
    made_tables = 0
    if group == "restaurant" and tables:
        area = DiningArea.objects.for_company(company).first() or DiningArea.objects.create(company=company, name="Main hall")
        existing = DiningTable.objects.for_company(company).count()
        for n in range(existing + 1, existing + 1 + min(tables, MAX_TABLES)):
            DiningTable.objects.create(company=company, area=area, name=f"T{n}")
            made_tables += 1
    return created, made_tables


def pos_url(company):
    return {"restaurant": "webapp:restaurant_dashboard", "retail": "webapp:pos"}.get(_group(company), "webapp:dashboard")


@login_required
@require_permission("tenants.manage_roles")
def setup_wizard(request, step="business"):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if step not in STEPS:
        return redirect("webapp:setup", step="business")
    group = _group(company)
    context = {"step": step, "steps": STEPS[:3], "step_no": STEPS.index(step) + 1, "group": group}

    if request.method == "POST" and request.POST.get("skip_all"):
        company.onboarding_completed_at = timezone.now()
        company.save(update_fields=["onboarding_completed_at"])
        messages.info(request, _("Setup skipped. You can come back to it any time from Settings."))
        return redirect("webapp:dashboard")

    if step == "business":
        form = BusinessStepForm(request.POST or None, request.FILES or None, instance=company)
        if request.method == "POST" and form.is_valid():
            form.save()
            return redirect("webapp:setup", step="catalog")
        context["form"] = form

    elif step == "catalog":
        from apps.verticals.restaurant.models import DiningTable, RestaurantMenuItem
        if request.method == "POST":
            rows, errors = read_rows(request.POST)
            try:
                tables = max(0, min(int(request.POST.get("tables") or 0), MAX_TABLES))
            except ValueError:
                tables = 0
            if request.POST.get("sample_menu") and group == "restaurant":
                from django.core.management import call_command
                call_command("seed_restaurant_demo", company_slug=company.slug)
            if errors:
                for error in errors:
                    messages.error(request, error)
            else:
                try:
                    created, made_tables = add_catalog(company, rows, group=group, tables=tables)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    if created or made_tables:
                        messages.success(request, _("Added %(items)s items and %(tables)s tables.") % {
                            "items": created, "tables": made_tables})
                    return redirect("webapp:setup", step="devices")
            post = request.POST
            keys = ["item_name", "item_price", "item_stock", "item_code", "item_category"]
            columns = [post.getlist(k)[:MAX_ROWS] for k in keys]
            context["rows"] = [dict(zip(["name", "price", "stock", "code", "category"],
                                        [col[i] if i < len(col) else "" for col in columns]))
                               for i in range(len(columns[0]))] or None
        products = Product.objects.for_company(company).filter(is_active=True)
        context.update({
            "product_count": products.count(),
            "recent": products.order_by("-id")[:8],
            "table_count": DiningTable.objects.for_company(company).count() if group == "restaurant" else 0,
            "menu_count": RestaurantMenuItem.objects.for_company(company).count() if group == "restaurant" else 0,
        })
        context["rows"] = context.get("rows") or [{} for _i in range(5)]

    elif step == "devices":
        if request.method == "POST":
            return redirect("webapp:setup", step="done")

    elif step == "done":
        if not company.onboarding_completed_at:
            company.onboarding_completed_at = timezone.now()
            company.save(update_fields=["onboarding_completed_at"])
        context["pos_url"] = pos_url(company)

    return render(request, "webapp/onboarding/wizard.html", context)
