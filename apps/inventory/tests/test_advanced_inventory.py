"""
Phase 31 — Advanced Inventory: Batch, Expiry, Serial and Stock Counts.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


@pytest.fixture
def batch_product(tenant_a):
    from apps.inventory.models import Product, Unit
    unit = Unit.objects.create(company=tenant_a, name="pcs")
    return Product.objects.create(
        company=tenant_a, sku="PROT-1", name="Whey Protein 1kg", unit=unit,
        cost_price=Decimal("20.00"), selling_price=Decimal("40.00"), tracking_type="batch",
    )


@pytest.fixture
def serial_product(tenant_a):
    from apps.inventory.models import Product, Unit
    unit = Unit.objects.create(company=tenant_a, name="pcs")
    return Product.objects.create(
        company=tenant_a, sku="PHONE-1", name="Phone X", unit=unit,
        cost_price=Decimal("300.00"), selling_price=Decimal("500.00"), tracking_type="serial",
    )


@pytest.fixture
def warehouse_a(tenant_a):
    from apps.inventory.models import Warehouse
    return Warehouse.objects.create(company=tenant_a, name="Main", is_default=True)


@pytest.fixture
def warehouse_a2(tenant_a):
    from apps.inventory.models import Warehouse
    return Warehouse.objects.create(company=tenant_a, name="Branch 2")


class TestBatchStock:
    def test_batch_stock_reconciles_by_warehouse(self, tenant_a, batch_product, warehouse_a, warehouse_a2):
        from apps.inventory.services import create_batch, receive_batch_stock, available_batch_quantity

        batch = create_batch(company=tenant_a, product=batch_product, batch_number="B1", expiry_date="2027-01-01")
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=100)
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a2, batch=batch, quantity=50)

        assert available_batch_quantity(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch) == Decimal("100")
        assert available_batch_quantity(company=tenant_a, product=batch_product, warehouse=warehouse_a2, batch=batch) == Decimal("50")
        assert batch_product.current_stock() == 150

    def test_create_batch_rejects_non_batch_product(self, tenant_a, warehouse_a):
        from apps.inventory.models import Product, Unit
        from apps.inventory.services import create_batch

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        basic_product = Product.objects.create(company=tenant_a, sku="X-1", name="Basic Widget", unit=unit)
        with pytest.raises(ValidationError, match="not batch-tracked"):
            create_batch(company=tenant_a, product=basic_product, batch_number="B1")

    def test_insufficient_batch_stock_cannot_be_sold(self, tenant_a, batch_product, warehouse_a):
        from apps.inventory.services import create_batch, receive_batch_stock, sell_batch_stock

        batch = create_batch(company=tenant_a, product=batch_product, batch_number="B1", expiry_date="2027-01-01")
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=5)

        with pytest.raises(ValidationError, match="Insufficient stock"):
            sell_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=10)

    def test_expired_batch_cannot_be_sold_when_policy_forbids(self, tenant_a, batch_product, warehouse_a):
        from apps.inventory.services import create_batch, receive_batch_stock, sell_batch_stock

        batch = create_batch(company=tenant_a, product=batch_product, batch_number="EXP1", expiry_date="2020-01-01")
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=10)

        with pytest.raises(ValidationError, match="expired"):
            sell_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=1)

    def test_expired_batch_sale_allowed_when_policy_permits(self, tenant_a, batch_product, warehouse_a):
        from apps.inventory.services import create_batch, receive_batch_stock, sell_batch_stock

        batch_product.block_expired_batch_sale = False
        batch_product.save(update_fields=["block_expired_batch_sale"])
        batch = create_batch(company=tenant_a, product=batch_product, batch_number="EXP2", expiry_date="2020-01-01")
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=10)

        movement = sell_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=3)
        assert movement.quantity == Decimal("-3")

    def test_fefo_suggestion_orders_by_expiry_and_never_mutates_state(self, tenant_a, batch_product, warehouse_a):
        from apps.inventory.services import create_batch, receive_batch_stock, suggest_fefo_batches

        late = create_batch(company=tenant_a, product=batch_product, batch_number="LATE", expiry_date="2028-01-01")
        early = create_batch(company=tenant_a, product=batch_product, batch_number="EARLY", expiry_date="2026-06-01")
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=late, quantity=10)
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=early, quantity=10)

        suggestions = suggest_fefo_batches(company=tenant_a, product=batch_product, warehouse=warehouse_a)
        assert [s["batch"].batch_number for s in suggestions] == ["EARLY", "LATE"]

        # Purely informational — nothing got sold or reserved.
        from apps.inventory.services import available_batch_quantity
        assert available_batch_quantity(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=early) == Decimal("10")


class TestSerialStock:
    def test_register_and_sell_serial(self, tenant_a, serial_product, warehouse_a):
        from apps.inventory.services import register_serial, sell_serial_stock

        serial = register_serial(company=tenant_a, product=serial_product, warehouse=warehouse_a, serial_number="IMEI-001")
        assert serial.status == "in_stock"

        sell_serial_stock(company=tenant_a, product=serial_product, serial=serial)
        serial.refresh_from_db()
        assert serial.status == "sold"
        assert serial_product.current_stock() == 0

    def test_serial_cannot_be_sold_twice(self, tenant_a, serial_product, warehouse_a):
        from apps.inventory.services import register_serial, sell_serial_stock

        serial = register_serial(company=tenant_a, product=serial_product, warehouse=warehouse_a, serial_number="IMEI-002")
        sell_serial_stock(company=tenant_a, product=serial_product, serial=serial)

        with pytest.raises(ValidationError, match="not available for sale"):
            sell_serial_stock(company=tenant_a, product=serial_product, serial=serial)

    def test_duplicate_serial_number_rejected_on_registration(self, tenant_a, serial_product, warehouse_a):
        from apps.inventory.services import register_serial

        register_serial(company=tenant_a, product=serial_product, warehouse=warehouse_a, serial_number="IMEI-003")
        with pytest.raises(ValidationError, match="already registered"):
            register_serial(company=tenant_a, product=serial_product, warehouse=warehouse_a, serial_number="IMEI-003")

    def test_returned_serial_restores_to_in_stock_status_variant(self, tenant_a, serial_product, warehouse_a):
        from apps.inventory.services import register_serial, sell_serial_stock, restore_serial_stock

        serial = register_serial(company=tenant_a, product=serial_product, warehouse=warehouse_a, serial_number="IMEI-004")
        sell_serial_stock(company=tenant_a, product=serial_product, serial=serial)
        restore_serial_stock(company=tenant_a, product=serial_product, serial=serial, warehouse=warehouse_a)

        serial.refresh_from_db()
        assert serial.status == "returned"
        assert serial_product.current_stock() == 1


class TestSalesIntegration:
    def test_invoice_sells_from_specified_batch_and_return_restores_it(self, tenant_a, tenant_a_owner, batch_product, warehouse_a):
        from apps.inventory.services import create_batch, receive_batch_stock, available_batch_quantity
        from apps.sales.services import create_invoice, process_return
        from apps.customers.models import Customer

        customer = Customer.objects.create(company=tenant_a, name="Walk-in")
        batch = create_batch(company=tenant_a, product=batch_product, batch_number="SB1", expiry_date="2027-01-01")
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=20)

        invoice = create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=customer, date="2026-01-01",
            lines=[{"product": batch_product, "quantity": Decimal("5"), "unit_price": Decimal("40.00"), "batch": batch}],
            warehouse=warehouse_a,
        )
        assert available_batch_quantity(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch) == Decimal("15")

        process_return(
            company=tenant_a, user=tenant_a_owner, invoice=invoice, date="2026-01-05",
            lines=[{"product": batch_product, "quantity": Decimal("2"), "unit_price": Decimal("40.00")}],
            warehouse=warehouse_a,
        )
        # No explicit batch on the return line -> resolved from the original invoice line.
        assert available_batch_quantity(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch) == Decimal("17")

    def test_invoice_sells_serial_and_blocks_reselling_it(self, tenant_a, tenant_a_owner, serial_product, warehouse_a):
        from apps.inventory.services import register_serial
        from apps.sales.services import create_invoice
        from apps.customers.models import Customer

        customer = Customer.objects.create(company=tenant_a, name="Walk-in")
        serial = register_serial(company=tenant_a, product=serial_product, warehouse=warehouse_a, serial_number="IMEI-100")

        create_invoice(
            company=tenant_a, user=tenant_a_owner, customer=customer, date="2026-01-01",
            lines=[{"product": serial_product, "quantity": Decimal("1"), "unit_price": Decimal("500.00"), "serial": serial}],
            warehouse=warehouse_a,
        )
        serial.refresh_from_db()
        assert serial.status == "sold"

        with pytest.raises(ValidationError, match="not available for sale"):
            create_invoice(
                company=tenant_a, user=tenant_a_owner, customer=customer, date="2026-01-02",
                lines=[{"product": serial_product, "quantity": Decimal("1"), "unit_price": Decimal("500.00"), "serial": serial}],
                warehouse=warehouse_a,
            )


class TestStockTransfer:
    def test_transfer_moves_stock_between_warehouses(self, tenant_a, tenant_a_owner, warehouse_a, warehouse_a2):
        from apps.inventory.models import Product, Unit
        from apps.inventory.services import record_stock_movement, create_stock_transfer

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        product = Product.objects.create(company=tenant_a, sku="T-1", name="Widget", unit=unit)
        record_stock_movement(company=tenant_a, product=product, warehouse=warehouse_a, quantity=Decimal("50"), reason="purchase")

        create_stock_transfer(
            company=tenant_a, user=tenant_a_owner, product=product,
            from_warehouse=warehouse_a, to_warehouse=warehouse_a2, quantity=Decimal("20"),
        )
        assert product.current_stock(warehouse=warehouse_a) == Decimal("30")
        assert product.current_stock(warehouse=warehouse_a2) == Decimal("20")
        assert product.current_stock() == Decimal("50")  # unchanged company-wide total

    def test_transfer_rejects_insufficient_stock(self, tenant_a, tenant_a_owner, warehouse_a, warehouse_a2):
        from apps.inventory.models import Product, Unit
        from apps.inventory.services import create_stock_transfer

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        product = Product.objects.create(company=tenant_a, sku="T-2", name="Widget 2", unit=unit)
        with pytest.raises(ValidationError, match="Insufficient stock"):
            create_stock_transfer(
                company=tenant_a, user=tenant_a_owner, product=product,
                from_warehouse=warehouse_a, to_warehouse=warehouse_a2, quantity=Decimal("5"),
            )


class TestStockAdjustmentAndCount:
    def test_adjustment_writes_audit_log(self, tenant_a, tenant_a_owner, warehouse_a):
        from apps.inventory.models import Product, Unit
        from apps.inventory.services import create_stock_adjustment
        from apps.audit.models import AuditLog

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        product = Product.objects.create(company=tenant_a, sku="A-1", name="Adjustable", unit=unit)

        movement = create_stock_adjustment(
            company=tenant_a, user=tenant_a_owner, product=product, warehouse=warehouse_a,
            quantity_delta=Decimal("-3"), reason_note="Damaged in storage",
        )
        assert product.current_stock() == Decimal("-3")
        assert AuditLog.objects.filter(company=tenant_a, action="stock_adjustment", object_id=str(movement.id)).exists()

    def test_stock_count_completion_reconciles_and_audits(self, tenant_a, tenant_a_owner, warehouse_a):
        from apps.inventory.models import Product, Unit
        from apps.inventory.services import (
            record_stock_movement, start_stock_count, submit_stock_count_line, complete_stock_count,
        )
        from apps.audit.models import AuditLog

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        product = Product.objects.create(company=tenant_a, sku="C-1", name="Counted Widget", unit=unit)
        record_stock_movement(company=tenant_a, product=product, warehouse=warehouse_a, quantity=Decimal("100"), reason="purchase")

        count = start_stock_count(company=tenant_a, user=tenant_a_owner, warehouse=warehouse_a, products=[product])
        line = count.lines.get(product=product)
        assert line.system_quantity == Decimal("100")

        submit_stock_count_line(company=tenant_a, stock_count_line=line, counted_quantity=Decimal("97"), notes="3 damaged")
        complete_stock_count(company=tenant_a, user=tenant_a_owner, stock_count=count)

        assert product.current_stock(warehouse=warehouse_a) == Decimal("97")
        count.refresh_from_db()
        assert count.status == "completed"
        assert AuditLog.objects.filter(company=tenant_a, action="complete_stock_count", object_id=str(count.id)).exists()

    def test_completing_a_count_twice_is_rejected(self, tenant_a, tenant_a_owner, warehouse_a):
        from apps.inventory.models import Product, Unit
        from apps.inventory.services import start_stock_count, complete_stock_count

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        product = Product.objects.create(company=tenant_a, sku="C-2", name="Widget", unit=unit)
        count = start_stock_count(company=tenant_a, user=tenant_a_owner, warehouse=warehouse_a, products=[product])
        complete_stock_count(company=tenant_a, user=tenant_a_owner, stock_count=count)

        with pytest.raises(ValidationError, match="already been completed"):
            complete_stock_count(company=tenant_a, user=tenant_a_owner, stock_count=count)

    def test_lines_with_no_count_submitted_are_skipped(self, tenant_a, tenant_a_owner, warehouse_a):
        from apps.inventory.models import Product, Unit
        from apps.inventory.services import record_stock_movement, start_stock_count, complete_stock_count

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        product = Product.objects.create(company=tenant_a, sku="C-3", name="Uncounted", unit=unit)
        record_stock_movement(company=tenant_a, product=product, warehouse=warehouse_a, quantity=Decimal("10"), reason="purchase")

        count = start_stock_count(company=tenant_a, user=tenant_a_owner, warehouse=warehouse_a, products=[product])
        complete_stock_count(company=tenant_a, user=tenant_a_owner, stock_count=count)
        assert product.current_stock(warehouse=warehouse_a) == Decimal("10")  # untouched


class TestExpiryNotifications:
    def test_expired_batch_with_stock_notifies_once(self, tenant_a, batch_product, warehouse_a):
        from apps.inventory.services import create_batch, receive_batch_stock, check_batch_expiry_and_notify
        from apps.inventory.models import BatchAlertLog

        batch = create_batch(company=tenant_a, product=batch_product, batch_number="EXPN", expiry_date="2020-01-01")
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=5)

        first = check_batch_expiry_and_notify(tenant_a)
        assert len(first) == 1
        assert BatchAlertLog.objects.filter(company=tenant_a, batch=batch, alert_type="expired").exists()

        second = check_batch_expiry_and_notify(tenant_a)
        assert len(second) == 0  # no repeat notification on a second run

    def test_batch_with_zero_stock_does_not_notify(self, tenant_a, batch_product, warehouse_a):
        from apps.inventory.services import create_batch, check_batch_expiry_and_notify

        create_batch(company=tenant_a, product=batch_product, batch_number="EMPTY", expiry_date="2020-01-01")
        result = check_batch_expiry_and_notify(tenant_a)
        assert result == []


class TestInventoryApi:
    def test_owner_can_create_batch_and_transfer_stock(self, tenant_a, as_tenant_a_owner, batch_product, warehouse_a, warehouse_a2):
        resp = as_tenant_a_owner.post("/api/inventory/batches/", {
            "product": batch_product.id, "batch_number": "API-1", "expiry_date": "2027-01-01",
        })
        assert resp.status_code == 201, resp.data

        from apps.inventory.services import receive_batch_stock
        from apps.inventory.models import ProductBatch
        batch = ProductBatch.objects.get(id=resp.data["id"])
        receive_batch_stock(company=tenant_a, product=batch_product, warehouse=warehouse_a, batch=batch, quantity=10)

        resp = as_tenant_a_owner.post("/api/inventory/stock-transfer/", {
            "product": batch_product.id, "from_warehouse": warehouse_a.id, "to_warehouse": warehouse_a2.id,
            "quantity": "4", "batch": batch.id,
        })
        assert resp.status_code == 201, resp.data

    def test_stock_adjustment_endpoint_requires_manage_permission(self, tenant_a, member_factory, warehouse_a):
        from conftest import jwt_client
        from apps.inventory.models import Product, Unit

        unit = Unit.objects.create(company=tenant_a, name="pcs")
        product = Product.objects.create(company=tenant_a, sku="API-A", name="Widget", unit=unit)

        accountant = member_factory(tenant_a, "Accountant")
        client = jwt_client(accountant)
        resp = client.post("/api/inventory/stock-adjustment/", {
            "product": product.id, "warehouse": warehouse_a.id, "quantity_delta": "5",
        })
        assert resp.status_code == 403  # Accountant has no inventory.manage_stock

    def test_cross_tenant_batch_rejected(self, tenant_a, tenant_b, as_tenant_a_owner):
        from apps.inventory.models import Product, Unit
        unit_b = Unit.objects.create(company=tenant_b, name="pcs")
        foreign_product = Product.objects.create(company=tenant_b, sku="F-1", name="Foreign", unit=unit_b, tracking_type="batch")

        resp = as_tenant_a_owner.post("/api/inventory/batches/", {
            "product": foreign_product.id, "batch_number": "X",
        })
        assert resp.status_code in (400, 403, 404)
