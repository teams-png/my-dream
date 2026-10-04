"""
Kerala restaurant starter kit: a new restaurant opens with a full Kerala menu (with pictures), categories,
kitchen stations, tables, add-ons, sample staff and last month's sample expenses — so the POS, KOT,
website and reports have something to show on day one. Everything is recorded in StarterSample and can be
removed in one click; anything already used in a bill is kept and switched off instead.
"""
import datetime
import logging
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from . import kerala_menu as data
from .models import (DiningArea, DiningTable, KitchenStation, MenuModifier, MenuModifierGroup, MenuModifierOption,
                     RestaurantMenuItem, StarterSample)

log = logging.getLogger(__name__)
ART_DIR = Path(settings.BASE_DIR) / "static" / "restaurant" / "kerala"
KIT_TYPES = {"restaurant", "catering_company", "cafe_juice_shop"}
SKU_PREFIX = "KL-"


def enabled():
    return getattr(settings, "RESTAURANT_STARTER_KIT", True)


def has_kit(company):
    return StarterSample.objects.for_company(company).exists()


def counts(company):
    rows = StarterSample.objects.for_company(company).values_list("kind", flat=True)
    out = {}
    for kind in rows:
        out[kind] = out.get(kind, 0) + 1
    return out


def _factor(company):
    return Decimal(str(data.CURRENCY_FACTORS.get((company.default_currency or "QAR").upper(), 1)))


def _money(company, qar):
    value = Decimal(str(qar)) * _factor(company)
    step = Decimal("1") if value >= 50 else (Decimal("0.5") if value >= 1 else Decimal("0.05"))
    return ((value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step).quantize(Decimal("0.01"))


def _image_name(code):
    """One shared copy of each picture in media storage; every restaurant's dish points at it."""
    name = f"restaurant/kerala/{code}.png"
    try:
        if not default_storage.exists(name):
            default_storage.save(name, ContentFile((ART_DIR / f"{code}.png").read_bytes()))
    except (OSError, FileNotFoundError):
        log.warning("Kerala menu picture %s is missing", code)
        return ""
    return name


def _track(company, kind, obj):
    StarterSample.objects.create(company=company, kind=kind, object_id=obj.pk)


@transaction.atomic
def install(company, user=None, *, staff=True, expenses=True):
    """Adds the Kerala starter kit. Safe to run again: dishes that already exist are skipped."""
    from apps.inventory.models import Product, ProductCategory, Unit
    code = company.business_type.code
    categories = [c for c in data.CATEGORIES if code != "cafe_juice_shop" or c[0] in data.CAFE_CATEGORIES]
    unit = Unit.objects.for_company(company).filter(name__in=["plate", "pcs", "piece"]).first() or \
        Unit.objects.create(company=company, name="plate")

    stations = {}
    for name, colour in data.STATIONS.items():
        if not any(c[1] == name for c in categories):
            continue
        station = KitchenStation.objects.for_company(company).filter(name=name).first()
        if station is None:
            station = KitchenStation.objects.create(company=company, name=name, colour=colour)
            _track(company, "station", station)
        stations[name] = station

    made = 0
    category_objs = {}
    for position, (cat_name, station_name) in enumerate(categories):
        category = ProductCategory.objects.for_company(company).filter(name=cat_name).first()
        if category is None:
            category = ProductCategory.objects.create(company=company, name=cat_name)
            _track(company, "category", category)
        category_objs[cat_name] = category
        stations[station_name].categories.add(category)
        for order, (dish, name, ml, price, desc, veg, spice, prep, featured, _art, _colour) in enumerate(data.DISHES[cat_name]):
            sku = f"{SKU_PREFIX}{dish}"[:50]
            if Product.objects.for_company(company).filter(sku=sku).exists():
                continue
            product = Product.objects.create(
                company=company, sku=sku, name=name, category=category, unit=unit, selling_price=_money(company, price),
                cost_price=(_money(company, price) * Decimal("0.4")).quantize(Decimal("0.01")),
                is_stock_tracked=False, tracking_type="none", is_active=True)
            item = RestaurantMenuItem(company=company, product=product, description=f"{desc} · {ml}",
                                      preparation_minutes=prep, spice_level=spice, is_vegetarian=veg,
                                      is_featured=featured, is_available=True, is_quick=dish in data.QUICK,
                                      sort_order=position * 100 + order)
            item.image.name = _image_name(dish)
            item.save()
            _track(company, "dish", product)
            made += 1

    for group_name, spec in data.MODIFIERS.items():
        targets = [c for c in spec["categories"] if c in category_objs]
        if not targets or MenuModifierGroup.objects.for_company(company).filter(name=group_name).exists():
            continue
        group = MenuModifierGroup.objects.create(company=company, name=group_name, is_required=spec["required"],
                                                 min_selections=0, max_selections=spec["max"])
        _track(company, "modifier_group", group)
        for i, (option, extra) in enumerate(spec["options"]):
            modifier = MenuModifier.objects.create(company=company, name=option, price_delta=_money(company, extra) if extra else 0)
            _track(company, "modifier", modifier)
            MenuModifierOption.objects.create(company=company, group=group, modifier=modifier, sort_order=i)
        for item in RestaurantMenuItem.objects.for_company(company).filter(product__category__name__in=targets,
                                                                          product__sku__startswith=SKU_PREFIX):
            item.modifier_groups.add(group)

    if not DiningTable.objects.for_company(company).exists():
        for area_name, prefix, how_many, seats in data.TABLES:
            area = DiningArea.objects.for_company(company).filter(name=area_name).first()
            if area is None:
                area = DiningArea.objects.create(company=company, name=area_name)
                _track(company, "area", area)
            for n in range(1, how_many + 1):
                table = DiningTable.objects.create(company=company, area=area, name=f"{prefix}{n}", capacity=seats)
                _track(company, "table", table)

    if staff:
        _install_staff(company)
    if expenses:
        _install_expenses(company, user)
    return made


def _install_staff(company):
    from apps.employees.models import Department, Designation, Employee, WorkShift
    if Employee.objects.for_company(company).exists():
        return
    shifts = {}
    for name, start, end in data.SHIFTS:
        shift, created = WorkShift.objects.for_company(company).get_or_create(
            name=name, defaults={"company": company, "start_time": start, "end_time": end, "working_days": [0, 1, 2, 3, 4, 5, 6]})
        if created:
            _track(company, "shift", shift)
        shifts[name] = shift
    joined = timezone.localdate() - datetime.timedelta(days=200)
    for i, (name, role, department, salary, shift) in enumerate(data.STAFF):
        dept, created = Department.objects.for_company(company).get_or_create(name=department, defaults={"company": company})
        if created:
            _track(company, "department", dept)
        designation, created = Designation.objects.for_company(company).get_or_create(name=role.capitalize(), defaults={"company": company})
        if created:
            _track(company, "designation", designation)
        employee = Employee.objects.create(
            company=company, name=f"{name} (sample)", phone=f"+974 5000 {1001 + i}", role_title=role,
            salary=_money(company, salary), joined_date=joined + datetime.timedelta(days=i * 9), department=dept,
            designation=designation, shift=shifts[shift])
        _track(company, "employee", employee)


def _install_expenses(company, user):
    from apps.expenses.models import ExpenseCategory
    from apps.expenses.services import record_expense
    if user is None:
        membership = company.memberships.select_related("user").filter(role__name="Owner").first()
        user = membership.user if membership else None
    if user is None:
        return
    first_of_month = timezone.localdate().replace(day=1)
    last_month = (first_of_month - datetime.timedelta(days=1)).replace(day=1)
    # the owner's opening cash pays for the sample expenses, so the books never start with negative cash
    from apps.accounting.models import Account
    from apps.accounting.services import post_journal_entry
    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["1000", "3000"])}
    if len(accounts) == 2:
        capital = _money(company, data.OPENING_CAPITAL)
        entry = post_journal_entry(company=company, date=last_month, user=user,
                                   lines=[(accounts["1000"], capital, Decimal("0")), (accounts["3000"], Decimal("0"), capital)],
                                   reference="Opening cash (sample)", memo="Kerala starter kit sample opening balance",
                                   source_type="starter_kit")
        _track(company, "journal", entry)
    for category_name, description, amount, day in data.EXPENSES:
        category, created = ExpenseCategory.objects.for_company(company).get_or_create(name=category_name, defaults={"company": company})
        if created:
            _track(company, "expense_category", category)
        expense = record_expense(company=company, user=user, category=category, date=last_month.replace(day=day),
                                 amount=_money(company, amount), description=f"{description} (sample)", payment_method="cash")
        _track(company, "expense", expense)


def install_for_new_company(company, user):
    """Called from company sign-up. Never blocks sign-up: a problem here is logged and skipped."""
    if not enabled() or company.business_type.code not in KIT_TYPES:
        return 0
    try:
        with transaction.atomic():
            return install(company, user)
    except Exception:
        log.exception("Kerala starter kit failed for company %s", company.pk)
        return 0


# ------------------------------------------------------------------ remove

@transaction.atomic
def remove(company):
    """Deletes what the kit added. Dishes and staff already used in bills / payroll are switched off instead."""
    from apps.employees.models import Department, Designation, Employee, WorkShift
    from apps.expenses.models import Expense, ExpenseCategory
    from apps.inventory.models import Product, ProductCategory
    rows = StarterSample.objects.for_company(company)
    ids = {}
    for kind, object_id in rows.values_list("kind", "object_id"):
        ids.setdefault(kind, []).append(object_id)
    kept = 0

    from apps.accounting.models import JournalEntry
    JournalEntry.objects.for_company(company).filter(id__in=ids.get("journal", [])).update(is_void=True)
    for expense in Expense.objects.for_company(company).filter(id__in=ids.get("expense", [])):
        if expense.journal_entry_id:  # posted entries are voided, never deleted
            entry = expense.journal_entry
            entry.is_void = True
            entry.memo = (entry.memo + " · sample data removed").strip(" ·")
            entry.save(update_fields=["is_void", "memo"])
        expense.delete()

    def delete_or_keep(queryset, switch_off=None):
        nonlocal kept
        for obj in queryset:
            try:
                with transaction.atomic():
                    obj.delete()
            except ProtectedError:
                kept += 1
                if switch_off:
                    switch_off(obj)

    def deactivate_product(product):
        product.is_active = False
        product.save(update_fields=["is_active"])

    def deactivate_employee(employee):
        employee.is_active = False
        employee.employment_status = "inactive"
        employee.save(update_fields=["is_active", "employment_status"])

    delete_or_keep(Product.objects.for_company(company).filter(id__in=ids.get("dish", [])), deactivate_product)
    delete_or_keep(Employee.objects.for_company(company).filter(id__in=ids.get("employee", [])), deactivate_employee)
    delete_or_keep(MenuModifierGroup.objects.for_company(company).filter(id__in=ids.get("modifier_group", [])))
    delete_or_keep(MenuModifier.objects.for_company(company).filter(id__in=ids.get("modifier", [])))
    delete_or_keep(KitchenStation.objects.for_company(company).filter(id__in=ids.get("station", [])))
    from apps.verticals.restaurant.models import RestaurantOrder
    busy_tables = set(RestaurantOrder.objects.for_company(company).values_list("table_id", flat=True))
    delete_or_keep(DiningTable.objects.for_company(company).filter(id__in=ids.get("table", [])).exclude(id__in=busy_tables))
    delete_or_keep(DiningArea.objects.for_company(company).filter(id__in=ids.get("area", [])).filter(tables__isnull=True))
    delete_or_keep(ProductCategory.objects.for_company(company).filter(id__in=ids.get("category", []), product__isnull=True))
    delete_or_keep(ExpenseCategory.objects.for_company(company).filter(id__in=ids.get("expense_category", []), expense__isnull=True))
    delete_or_keep(Department.objects.for_company(company).filter(id__in=ids.get("department", []), employee__isnull=True))
    delete_or_keep(Designation.objects.for_company(company).filter(id__in=ids.get("designation", []), employee__isnull=True))
    delete_or_keep(WorkShift.objects.for_company(company).filter(id__in=ids.get("shift", []), employee__isnull=True))
    rows.delete()
    return kept
