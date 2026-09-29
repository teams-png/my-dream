from datetime import date, time
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import Product, ProductCategory, StockMovement
from apps.audit.models import AuditLog
from apps.inventory.services import record_stock_movement
from apps.modules.models import BusinessType
from apps.verticals.restaurant.models import DeliveryIntegration, DiningArea, DiningTable, FoodWaste, KitchenStation, MenuModifier, MenuModifierGroup, MenuModifierOption, RestaurantMenuItem, RestaurantOrder, RestaurantProfile, RecipeIngredient, TableReservation
from apps.verticals.restaurant import services


pytestmark = pytest.mark.django_db


@pytest.fixture
def restaurant_data(tenant_a, tenant_a_owner, sales_fixtures_factory):
    call_command("seed_platform")
    tenant_a.business_type = BusinessType.objects.get(code="restaurant")
    tenant_a.save(update_fields=["business_type"])
    base = sales_fixtures_factory(tenant_a, sku="INGREDIENT", stock_price=Decimal("10"))
    ingredient = base["product"]
    record_stock_movement(company=tenant_a, product=ingredient, warehouse=base["warehouse"], quantity=20, reason="purchase")
    menu = Product.objects.create(
        company=tenant_a, sku="MENU-BURGER", name="Burger", unit=base["unit"],
        cost_price=5, selling_price=20, is_stock_tracked=False, tracking_type="none",
    )
    RecipeIngredient.objects.create(company=tenant_a, menu_product=menu, ingredient_product=ingredient, quantity=2)
    area = DiningArea.objects.create(company=tenant_a, name="Main Hall")
    table = DiningTable.objects.create(company=tenant_a, area=area, name="T1")
    return {**base, "ingredient": ingredient, "menu": menu, "area": area, "table": table, "user": tenant_a_owner}


def test_dine_in_kot_and_recipe_stock_billing(tenant_a, restaurant_data):
    d = restaurant_data
    shift = services.open_shift(company=tenant_a, user=d["user"], opening_cash=100)
    order = services.create_order(company=tenant_a, channel="dine_in", table=d["table"], waiter=d["user"], shift=shift)
    extra = MenuModifier.objects.create(company=tenant_a, name="Extra cheese", price_delta=3)
    services.add_order_line(company=tenant_a, order=order, product=d["menu"], quantity=2, modifiers=[extra])
    ticket = services.send_to_kitchen(company=tenant_a, order=order)
    services.update_kitchen_status(company=tenant_a, ticket=ticket, status="preparing")
    services.update_kitchen_status(company=tenant_a, ticket=ticket, status="ready")
    invoice = services.settle_order(
        company=tenant_a, user=d["user"], order=order, warehouse=d["warehouse"], date=date.today(),
        payments=[{"method": "cash", "amount": Decimal("46")}],
    )
    order.refresh_from_db(); d["table"].refresh_from_db()
    assert invoice.total == Decimal("46")
    assert order.status == "paid" and d["table"].status == "cleaning"
    assert d["ingredient"].current_stock(d["warehouse"]) == Decimal("16")


def test_hold_resume_split_merge(tenant_a, restaurant_data):
    d = restaurant_data
    order = services.create_order(company=tenant_a, channel="takeaway", waiter=d["user"])
    first = services.add_order_line(company=tenant_a, order=order, product=d["menu"], quantity=1)
    second = services.add_order_line(company=tenant_a, order=order, product=d["ingredient"], quantity=1)
    services.set_order_held(company=tenant_a, order=order, held=True)
    services.set_order_held(company=tenant_a, order=order, held=False)
    split = services.split_order(company=tenant_a, order=order, line_ids=[second.id])
    assert split.lines.count() == 1 and order.lines.count() == 1
    services.merge_orders(company=tenant_a, target=order, source=split)
    split.refresh_from_db()
    assert order.lines.count() == 2 and split.status == "cancelled"


def test_restaurant_pages_and_shift_reconciliation(client, tenant_a, restaurant_data):
    d = restaurant_data
    client.force_login(d["user"])
    overview = client.get(reverse("webapp:restaurant_dashboard"))
    assert overview.status_code == 200
    assert b"restaurant-shortcuts" in overview.content
    setup = client.get(reverse("webapp:restaurant_setup"))
    assert setup.status_code == 200
    assert b"restaurant-shortcuts" in setup.content and b"restaurant-back" in setup.content
    assert client.get(reverse("webapp:restaurant_reservations")).status_code == 200
    assert client.get(reverse("webapp:restaurant_waste")).status_code == 200
    assert client.get(reverse("webapp:restaurant_reports")).status_code == 200
    shift = services.open_shift(company=tenant_a, user=d["user"], opening_cash=50)
    closed = services.close_shift(company=tenant_a, user=d["user"], shift=shift, actual_cash=50)
    assert closed.status == "closed" and closed.variance == 0


def test_signed_delivery_webhook_imports_order(client, tenant_a, restaurant_data):
    import hashlib, hmac, json
    d = restaurant_data
    integration = DeliveryIntegration.objects.create(
        company=tenant_a, provider="snoonu", store_id="STORE-1", is_enabled=True,
    )
    integration.set_secret("api_key", "key"); integration.set_secret("webhook_secret", "hook-secret"); integration.save()
    payload = {"external_order_id": "SN-100", "customer": {"name": "Guest", "phone": "555", "address": "Doha"}, "items": [{"sku": d["menu"].sku, "quantity": 1, "unit_price": "20"}]}
    body = json.dumps(payload).encode()
    signature = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    response = client.post(reverse("webapp:restaurant_delivery_webhook", args=[integration.webhook_token]), data=body, content_type="application/json", HTTP_X_DELIVERY_SIGNATURE=f"sha256={signature}")
    assert response.status_code == 200
    assert response.json()["status"] == "imported"


def test_visual_menu_quick_add_and_sold_out_protection(client, tenant_a, restaurant_data):
    d = restaurant_data
    client.force_login(d["user"])
    menu_item = RestaurantMenuItem.objects.create(
        company=tenant_a, product=d["menu"], description="House burger",
        preparation_minutes=12, is_featured=True,
    )
    order = services.create_order(company=tenant_a, channel="takeaway", waiter=d["user"])
    url = reverse("webapp:restaurant_order_detail", args=[order.id])
    response = client.get(url)
    assert response.status_code == 200
    assert b"House burger" in response.content and b"Restaurant POS" in response.content
    assert b'data-has-modifiers="false"' in response.content
    assert b"updateCart(formDataForQuickAdd" in response.content
    response = client.post(url, {"action": "quick_add", "product_id": d["menu"].id, "quantity": 2})
    assert response.status_code == 302
    assert order.lines.get().quantity == 2
    menu_item.is_available = False
    menu_item.save(update_fields=["is_available"])
    client.post(url, {"action": "quick_add", "product_id": d["menu"].id, "quantity": 1})
    assert order.lines.count() == 1


def test_modifier_group_rules_and_station_kot(tenant_a, restaurant_data):
    d = restaurant_data
    item = RestaurantMenuItem.objects.create(company=tenant_a, product=d["menu"])
    group = MenuModifierGroup.objects.create(company=tenant_a, name="Choose cheese", is_required=True, min_selections=1, max_selections=1)
    cheese = MenuModifier.objects.create(company=tenant_a, name="Cheddar", price_delta=2)
    MenuModifierOption.objects.create(company=tenant_a, group=group, modifier=cheese)
    item.modifier_groups.add(group)
    station = KitchenStation.objects.create(company=tenant_a, name="Grill")
    order = services.create_order(company=tenant_a, channel="takeaway", waiter=d["user"])
    with pytest.raises(Exception):
        services.add_order_line(company=tenant_a, order=order, product=d["menu"], quantity=1)
    services.add_order_line(company=tenant_a, order=order, product=d["menu"], quantity=1, modifiers=[cheese])
    ticket = services.send_to_kitchen(company=tenant_a, order=order)
    assert ticket.station == station


def test_food_waste_reservation_and_public_qr(client, tenant_a, restaurant_data):
    d = restaurant_data
    client.force_login(d["user"])
    before = d["ingredient"].current_stock(d["warehouse"])
    waste = services.record_food_waste(company=tenant_a, user=d["user"], ingredient=d["ingredient"], warehouse=d["warehouse"], quantity=2, reason="spoiled")
    assert FoodWaste.objects.filter(id=waste.id).exists()
    assert d["ingredient"].current_stock(d["warehouse"]) == before - 2
    TableReservation.objects.create(company=tenant_a, customer_name="Guest", phone="555", reservation_at=timezone.now(), table=d["table"])
    assert client.get(reverse("webapp:restaurant_reservations")).status_code == 200
    RestaurantMenuItem.objects.create(company=tenant_a, product=d["menu"], description="Fresh burger")
    profile = RestaurantProfile.objects.create(company=tenant_a, tagline="Fresh every day")
    client.logout()
    assert client.get(reverse("webapp:restaurant_public_menu", args=[profile.public_menu_token])).status_code == 200
    qr = client.get(reverse("webapp:restaurant_public_menu_qr", args=[profile.public_menu_token]))
    assert qr.status_code == 200 and qr["Content-Type"] == "image/png"


def test_qr_self_order_scheduled_menu_and_public_status(client, tenant_a, restaurant_data):
    import json
    d = restaurant_data
    item = RestaurantMenuItem.objects.create(company=tenant_a, product=d["menu"], description="QR burger")
    profile = RestaurantProfile.objects.create(company=tenant_a, qr_ordering_enabled=True)
    response = client.post(
        reverse("webapp:restaurant_public_order", args=[profile.public_menu_token]),
        data=json.dumps({"name": "QR Guest", "phone": "777", "items": [{"product_id": d["menu"].id, "quantity": 2, "modifier_ids": []}]}),
        content_type="application/json",
    )
    assert response.status_code == 200
    order = RestaurantOrder.objects.for_company(tenant_a).get(order_number=response.json()["order_number"])
    assert order.status == "kitchen" and order.public_order_token
    assert client.get(response.json()["status_url"]).status_code == 200
    item.available_from = time(0, 0); item.available_until = time(0, 1); item.save(update_fields=["available_from", "available_until"])
    draft = services.create_order(company=tenant_a, channel="takeaway", waiter=d["user"])
    with pytest.raises(Exception): services.add_order_line(company=tenant_a, order=draft, product=d["menu"])


def test_audited_cancellation_and_z_report(client, tenant_a, restaurant_data):
    d = restaurant_data
    client.force_login(d["user"])
    shift = services.open_shift(company=tenant_a, user=d["user"], opening_cash=25)
    order = services.create_order(company=tenant_a, channel="dine_in", table=d["table"], waiter=d["user"], shift=shift)
    services.add_order_line(company=tenant_a, order=order, product=d["menu"])
    response = client.post(reverse("webapp:restaurant_order_cancel", args=[order.id]), {"reason": "Customer changed plans"})
    order.refresh_from_db(); d["table"].refresh_from_db()
    assert response.status_code == 302 and order.status == "cancelled"
    assert d["table"].status == "available"
    assert AuditLog.objects.filter(company=tenant_a, model_name="RestaurantOrder", object_id=str(order.id), action="cancel").exists()
    assert client.get(reverse("webapp:restaurant_z_report", args=[shift.id])).status_code == 200

@pytest.mark.django_db
def test_kitchen_ticket_cannot_skip_preparation(tenant_a):
    """Kitchen actions must move forward one step at a time."""
    from django.core.exceptions import ValidationError
    from apps.verticals.restaurant.models import KitchenTicket, RestaurantOrder
    from apps.verticals.restaurant.services import update_kitchen_status

    company = tenant_a
    order = RestaurantOrder.objects.create(company=company, order_number="KDS-TEST-1", channel="takeaway")
    ticket = KitchenTicket.objects.create(company=company, order=order, ticket_number="KDS-TEST-1")
    with pytest.raises(ValidationError):
        update_kitchen_status(company=company, ticket=ticket, status="ready")
    update_kitchen_status(company=company, ticket=ticket, status="preparing")
    update_kitchen_status(company=company, ticket=ticket, status="ready")
    order.refresh_from_db()
    assert order.status == "ready"

@pytest.mark.django_db
def test_sample_menu_is_opt_in_and_idempotent(tenant_a, restaurant_data):
    from apps.verticals.restaurant.management.commands.seed_restaurant_demo import SAMPLES
    assert not Product.objects.for_company(tenant_a).filter(sku__startswith="BP-DEMO-").exists()
    call_command("seed_restaurant_demo", company_slug=tenant_a.slug)
    call_command("seed_restaurant_demo", company_slug=tenant_a.slug)
    assert len(SAMPLES) == 20
    assert Product.objects.for_company(tenant_a).filter(sku__startswith="BP-DEMO-").count() == len(SAMPLES)
    assert ProductCategory.objects.for_company(tenant_a).filter(product__sku__startswith="BP-DEMO-").distinct().count() >= 10
    assert RestaurantMenuItem.objects.for_company(tenant_a).filter(product__sku__startswith="BP-DEMO-").exclude(image="").count() == len(SAMPLES)

@pytest.mark.django_db
def test_cashier_empty_order_and_demo_menu_flow(client, tenant_a, restaurant_data):
    client.force_login(restaurant_data["user"])
    order = services.create_order(company=tenant_a, channel="takeaway", waiter=restaurant_data["user"])
    pos_url = reverse("webapp:restaurant_order_detail", args=[order.pk])
    page = client.get(pos_url)
    assert page.status_code == 200
    assert b'Add sample menu' in page.content
    assert b'disabled title="Add an item to this draft order first"' in page.content
    empty_send = client.post(pos_url, {"action": "send_kitchen"})
    assert empty_send.status_code == 302
    order.refresh_from_db()
    assert order.status == "draft"
    seeded = client.post(reverse("webapp:restaurant_demo_menu"), {"order_id": order.pk})
    assert seeded.status_code == 302
    assert seeded.url == pos_url
    page = client.get(pos_url)
    assert b"Classic Burger" in page.content and b"Golden Fries" in page.content


def test_table_can_be_marked_ready_only_without_open_order(client, tenant_a, restaurant_data):
    d = restaurant_data
    client.force_login(d["user"])
    table = d["table"]
    url = reverse("webapp:restaurant_table_status", args=[table.id])
    order = services.create_order(company=tenant_a, channel="dine_in", table=table, waiter=d["user"])
    client.post(url, {"status": "available"})
    table.refresh_from_db()
    assert table.status == "occupied"  # still has an open order
    services.cancel_order(company=tenant_a, user=d["user"], order=order, reason="Guest left")
    DiningTable.objects.filter(pk=table.pk).update(status="cleaning")
    assert client.get(url).status_code == 405
    client.post(url, {"status": "available"})
    table.refresh_from_db()
    assert table.status == "available"
    client.post(url, {"status": "occupied"})
    table.refresh_from_db()
    assert table.status == "available"  # only safe statuses can be set by hand


def test_dashboard_floor_plan_and_table_preselect(client, tenant_a, restaurant_data):
    d = restaurant_data
    client.force_login(d["user"])
    order = services.create_order(company=tenant_a, channel="dine_in", table=d["table"], waiter=d["user"])
    page = client.get(reverse("webapp:restaurant_dashboard"))
    assert page.status_code == 200
    assert page.context["stats"]["active_orders"] == 1 and page.context["stats"]["tables_busy"] == 1
    assert reverse("webapp:restaurant_order_detail", args=[order.id]).encode() in page.content
    start = client.get(reverse("webapp:restaurant_order_add") + f"?table={d['table'].id}")
    assert start.context["form"]["channel"].value() == "dine_in"
    assert str(start.context["form"]["table"].value()) == str(d["table"].id)


def test_pos_creates_stock_location_for_billing(client, tenant_a, restaurant_data):
    from apps.inventory.models import Warehouse
    d = restaurant_data
    client.force_login(d["user"])
    Warehouse.objects.filter(company=tenant_a).update(is_active=False)
    order = services.create_order(company=tenant_a, channel="takeaway", waiter=d["user"])
    page = client.get(reverse("webapp:restaurant_order_detail", args=[order.id]))
    assert page.status_code == 200
    assert page.context["settle_form"].fields["warehouse"].queryset.exists()
