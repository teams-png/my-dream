"""Van sales: lines, loading the van, billing shops on credit, collecting dues, evening settlement, report."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from apps.customers.models import Customer
from apps.industry.models import VanRoute, VanRouteStop, VanTrip
from apps.inventory.models import Product, ProductPack, Unit, Warehouse
from apps.inventory.services import record_stock_movement
from apps.sales import services as sales
from apps.sales.models import SalesInvoice
from apps.subscriptions.pricing import plans_for
from apps.tenants.models import Role
from apps.tenants.services import invite_member
from apps.webapp.public_views import create_trial_account

pytestmark = pytest.mark.django_db


def _login(client, user, company):
    client.force_login(user)
    session = client.session
    session["active_company_id"] = company.id
    session.save()
    return client


@pytest.fixture
def shop():
    """A carton-box wholesaler: owner, two drivers, a product in stock, a line with two shops."""
    call_command("seed_platform")
    owner, company = create_trial_account(data={
        "business_name": "Box Supply", "business_type": "wholesale_business", "country": "India",
        "full_name": "Owner One", "email": "owner@box.test", "password": "Box-Pass-2026!",
        "plan": plans_for("India", "wholesale_business").last()})
    staff = Role.objects.get(company=company, name="Staff")
    drivers = []
    for n in (1, 2):
        user = get_user_model().objects.create_user(username=f"d{n}@box.test", email=f"d{n}@box.test",
                                                    password="Box-Pass-2026!", first_name=f"Driver{n}")
        invite_member(company=company, user=user, role=staff)
        drivers.append(user)
    warehouse = Warehouse.objects.for_company(company).filter(is_default=True).first() or \
        Warehouse.objects.for_company(company).first()
    unit = Unit.objects.for_company(company).first() or Unit.objects.create(company=company, name="pcs")
    box = Product.objects.create(company=company, sku="BOX-10", name="Carton 10x10", unit=unit,
                                 cost_price=Decimal("3"), selling_price=Decimal("5"))
    record_stock_movement(company=company, product=box, warehouse=warehouse, quantity=Decimal("100"), reason="purchase")
    a = Customer.objects.create(company=company, name="Shop A", phone="9000000001")
    b = Customer.objects.create(company=company, name="Shop B", phone="9000000002")
    route = VanRoute.objects.create(company=company, name="Monday line", driver=drivers[0])
    VanRouteStop.objects.create(route=route, customer=a, position=1)
    VanRouteStop.objects.create(route=route, customer=b, position=2)
    return {"company": company, "owner": owner, "drivers": drivers, "warehouse": warehouse, "box": box,
            "a": a, "b": b, "route": route}


def test_full_day_on_the_line(client, shop):
    company, box, a, b = shop["company"], shop["box"], shop["a"], shop["b"]
    # Shop B already owes 40 from last week
    sales.create_invoice(company=company, user=shop["owner"], customer=b, date="2026-10-01",
                         lines=[{"product": box, "quantity": Decimal("8"), "unit_price": Decimal("5")}],
                         warehouse=shop["warehouse"])
    _login(client, shop["owner"], company)
    assert client.get(reverse("webapp:van_home")).status_code == 200
    client.post(reverse("webapp:van_trip_start"), {"route": shop["route"].id, "driver": shop["drivers"][0].id})
    trip = VanTrip.objects.get(company=company, route=shop["route"])
    client.post(reverse("webapp:van_trip_action", args=[trip.id]), {"action": "load", "product": box.id, "quantity": "50"})
    assert trip.loads.get().loaded == 50

    driver = _login(client, shop["drivers"][0], company)
    page = driver.get(reverse("webapp:van_trip", args=[trip.id]))
    assert page.status_code == 200 and b"Shop A" in page.content and b"Shop B" in page.content
    sell = driver.get(reverse("webapp:van_sell", args=[trip.id]) + f"?customer={a.id}")
    assert sell.status_code == 200 and b"Carton 10x10" in sell.content
    r = driver.post(reverse("webapp:van_sell", args=[trip.id]),
                    {"customer": a.id, f"qty_{box.id}": "10", f"price_{box.id}": "5.00", "paid": "20", "method": "cash"})
    invoice = SalesInvoice.objects.get(company=company, customer=a)
    assert r.status_code == 302 and f"billed={invoice.id}" in r["Location"]
    assert invoice.total == Decimal("50.00") and invoice.amount_paid == Decimal("20.00") and invoice.status == "partial"
    assert box.current_stock(shop["warehouse"]) == Decimal("82")  # 100 - 8 (last week) - 10
    # old dues collected from Shop B
    driver.post(reverse("webapp:van_trip_action", args=[trip.id]),
                {"action": "collect", "customer": b.id, "amount": "40", "method": "cash"})
    assert SalesInvoice.objects.get(company=company, customer=b).status == "paid"
    # drivers can't settle
    driver.post(reverse("webapp:van_trip_action", args=[trip.id]), {"action": "close", "cash_handed": "0"})
    trip.refresh_from_db()
    assert trip.status == "out"

    owner = _login(client, shop["owner"], company)
    owner.post(reverse("webapp:van_trip_action", args=[trip.id]),
               {"action": "close", f"returned_{box.id}": "39", "cash_handed": "55"})
    trip.refresh_from_db()
    load = trip.loads.get()
    assert trip.status == "closed" and load.returned == 39
    assert box.current_stock(shop["warehouse"]) == Decimal("81")  # one carton missing from the van, written off
    report = owner.get(reverse("webapp:van_report"))
    driver_row = report.context["drivers"][0]
    assert driver_row["sales"] == Decimal("50.00") and driver_row["credit"] == Decimal("30.00")
    assert driver_row["collected"] == Decimal("40.00") and driver_row["expected_cash"] == Decimal("60.00")
    assert driver_row["cash_short"] == Decimal("5.00")


def test_van_limits_stock_credit_and_packs(client, shop):
    company, box, a = shop["company"], shop["box"], shop["a"]
    trip = VanTrip.objects.create(company=company, route=shop["route"], driver=shop["drivers"][0],
                                  date="2026-10-26", warehouse=shop["warehouse"])
    trip.loads.create(product=box, loaded=Decimal("20"))
    bundle = ProductPack.objects.create(company=company, product=box, name="Bundle", factor=Decimal("10"), selling_price=Decimal("45"))
    _login(client, shop["drivers"][0], company)
    url = reverse("webapp:van_sell", args=[trip.id])
    client.post(url, {"customer": a.id, f"qty_{box.id}": "3", f"unit_{box.id}": bundle.id, f"price_{box.id}": "45"})
    assert not SalesInvoice.objects.filter(customer=a).exists()  # 30 pieces, only 20 in the van
    client.post(url, {"customer": a.id, f"qty_{box.id}": "2", f"unit_{box.id}": bundle.id, f"price_{box.id}": "45"})
    line = SalesInvoice.objects.get(customer=a).lines.get()
    assert (line.unit_name, line.unit_factor, line.quantity) == ("Bundle", Decimal("10"), Decimal("2"))
    assert box.current_stock(shop["warehouse"]) == Decimal("80")
    # credit limit
    shop["b"].credit_limit = Decimal("10")
    shop["b"].save()
    trip.loads.update(loaded=Decimal("40"))
    client.post(url, {"customer": shop["b"].id, f"qty_{box.id}": "5", f"price_{box.id}": "5", "paid": "0"})
    assert not SalesInvoice.objects.filter(customer=shop["b"]).exists()
    client.post(url, {"customer": shop["b"].id, f"qty_{box.id}": "5", f"price_{box.id}": "5", "paid": "20"})
    assert SalesInvoice.objects.filter(customer=shop["b"]).exists()  # only 5 on credit: inside the limit


def test_drivers_only_see_their_own_trips(client, shop):
    company = shop["company"]
    trip = VanTrip.objects.create(company=company, route=shop["route"], driver=shop["drivers"][0],
                                  date="2026-10-26", warehouse=shop["warehouse"])
    other = _login(client, shop["drivers"][1], company)
    assert other.get(reverse("webapp:van_trip", args=[trip.id])).status_code == 404
    assert other.get(reverse("webapp:van_sell", args=[trip.id]) + f"?customer={shop['a'].id}").status_code == 404
    assert other.get(reverse("webapp:van_routes")).status_code == 404
    assert other.get(reverse("webapp:van_report")).status_code in (403, 404)
    home = other.get(reverse("webapp:van_home"))
    assert home.status_code == 200 and not home.context["rows"]


def test_lines_and_shops_setup(client, shop):
    company = shop["company"]
    _login(client, shop["owner"], company)
    client.post(reverse("webapp:van_routes"), {"name": "Thursday line", "driver": shop["drivers"][1].id, "days": ["3"]})
    route = VanRoute.objects.get(company=company, name="Thursday line")
    assert route.days == "3" and route.driver == shop["drivers"][1]
    url = reverse("webapp:van_route", args=[route.id])
    client.post(url, {"action": "add", "customer": shop["b"].id})
    client.post(url, {"action": "add", "new_name": "Shop C", "new_phone": "9000000003"})
    stops = list(route.stops.select_related("customer"))
    assert [s.customer.name for s in stops] == ["Shop B", "Shop C"]
    client.post(url, {"action": "up", "stop": stops[1].id})
    assert [s.customer.name for s in route.stops.select_related("customer")] == ["Shop C", "Shop B"]
    assert client.get(url).status_code == 200 and client.get(reverse("webapp:van_routes")).status_code == 200


def test_van_sales_only_for_its_business_types(client, tenant_a, tenant_a_owner):
    _login(client, tenant_a_owner, tenant_a)
    assert client.get(reverse("webapp:van_home")).status_code == 302
