from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import Account
from apps.accounting.services import account_balance
from apps.finance import services
from apps.finance.models import RecurringInvoice, RecurringInvoiceLine
from apps.inventory.models import Product
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db


@pytest.fixture
def data(tenant_a, tenant_a_owner, sales_fixtures_factory):
    base = sales_fixtures_factory(tenant_a)
    service = Product.objects.create(company=tenant_a, sku="SVC", name="Maintenance", unit=base["unit"],
                                     selling_price=500, is_stock_tracked=False, tracking_type="none")
    supplier = Supplier.objects.create(company=tenant_a, name="Kitchen Supplies Co")
    return {**base, "service": service, "supplier": supplier, "user": tenant_a_owner}


def bal(company, code):
    return account_balance(Account.objects.get(company=company, code=code))


def test_received_cheque_clears_into_bank_and_pays_invoice(tenant_a, data):
    from apps.sales.services import create_invoice
    invoice = create_invoice(company=tenant_a, user=data["user"], customer=data["customer"], date=date(2026, 9, 1),
                             lines=[{"product": data["service"], "quantity": 1, "unit_price": Decimal("500")}], warehouse=data["warehouse"])
    cheque = services.register_cheque(company=tenant_a, user=data["user"], direction="received", amount="500",
                                      cheque_number="000123", cheque_date=date(2026, 10, 15), customer=data["customer"], invoice=invoice)
    bank_before = bal(tenant_a, "1010")
    services.update_cheque_status(company=tenant_a, user=data["user"], cheque=cheque, status="deposited")
    assert bal(tenant_a, "1010") == bank_before  # nothing booked until the bank clears it
    services.update_cheque_status(company=tenant_a, user=data["user"], cheque=cheque, status="cleared", on=date(2026, 10, 16))
    invoice.refresh_from_db()
    assert bal(tenant_a, "1010") == bank_before + Decimal("500") and invoice.status == "paid"
    with pytest.raises(ValidationError):
        services.update_cheque_status(company=tenant_a, user=data["user"], cheque=cheque, status="bounced")


def test_issued_cheque_pays_supplier_from_bank_and_bounce_notifies(tenant_a, data):
    from apps.notifications.models import Notification
    cheque = services.register_cheque(company=tenant_a, user=data["user"], direction="issued", amount="200",
                                      cheque_number="900001", cheque_date=date(2026, 10, 1), supplier=data["supplier"])
    services.update_cheque_status(company=tenant_a, user=data["user"], cheque=cheque, status="cleared")
    assert bal(tenant_a, "1010") == Decimal("-200") and bal(tenant_a, "1000") == Decimal("0")
    second = services.register_cheque(company=tenant_a, user=data["user"], direction="received", amount="50",
                                      cheque_number="7", cheque_date=date(2026, 10, 1), customer=data["customer"])
    services.update_cheque_status(company=tenant_a, user=data["user"], cheque=second, status="bounced", reason="Insufficient funds")
    assert Notification.objects.filter(company=tenant_a, title__contains="bounced").exists()
    with pytest.raises(ValidationError):
        services.register_cheque(company=tenant_a, user=data["user"], direction="received", amount="10",
                                 cheque_number="8", cheque_date=date(2026, 10, 1))


def test_cheque_reminders_sent_once(tenant_a, data):
    services.register_cheque(company=tenant_a, user=data["user"], direction="received", amount="10",
                             cheque_number="1", cheque_date=date(2026, 10, 2), customer=data["customer"])
    assert services.send_cheque_reminders(today=date(2026, 9, 30)) == 1
    assert services.send_cheque_reminders(today=date(2026, 10, 1)) == 0


def test_recurring_invoice_catches_up_and_stops_at_end_date(tenant_a, data):
    rec = RecurringInvoice.objects.create(company=tenant_a, name="AMC", customer=data["customer"], warehouse=data["warehouse"],
                                          frequency="monthly", next_run_date=date(2026, 7, 31), end_date=date(2026, 10, 31),
                                          tax_percent=Decimal("5"), created_by=data["user"])
    RecurringInvoiceLine.objects.create(recurring=rec, product=data["service"], quantity=1, unit_price=Decimal("500"))
    created = services.run_recurring_invoice(rec, today=date(2026, 9, 30))
    assert [i.date for i in created] == [date(2026, 7, 31), date(2026, 8, 31), date(2026, 9, 30)]
    assert created[0].transaction_total == Decimal("525.00")
    rec.refresh_from_db()
    assert rec.next_run_date == date(2026, 10, 31) and rec.invoices_created == 3 and rec.is_active
    services.run_recurring_invoice(rec, today=date(2026, 12, 31))
    rec.refresh_from_db()
    assert rec.invoices_created == 4 and not rec.is_active


def test_fixed_asset_depreciation_and_disposal(tenant_a, data):
    asset = services.register_asset(company=tenant_a, user=data["user"], name="Oven", cost=Decimal("12000"),
                                     salvage_value=Decimal("0"), useful_life_months=12, purchase_date=date(2026, 1, 10), paid_from="bank")
    assert bal(tenant_a, "1500") == Decimal("12000") and bal(tenant_a, "1010") == Decimal("-12000")
    posted = services.run_depreciation(company=tenant_a, user=data["user"], up_to=date(2026, 3, 15))
    assert len(posted) == 3 and asset.monthly_depreciation == Decimal("1000.00")
    assert services.run_depreciation(company=tenant_a, user=data["user"], up_to=date(2026, 3, 31)) == []  # idempotent
    assert bal(tenant_a, "5300") == Decimal("3000")
    services.dispose_asset(company=tenant_a, user=data["user"], asset=asset, on=date(2026, 4, 20), amount=Decimal("9500"))
    asset.refresh_from_db()
    # April depreciation posted first: book value 8000, sold for 9500 -> gain 1500
    assert asset.status == "disposed" and bal(tenant_a, "4100") == Decimal("1500")
    assert bal(tenant_a, "1500") == Decimal("0") and bal(tenant_a, "1590") == Decimal("0")


def test_finance_pages_and_tenant_isolation(client, tenant_a, tenant_b, data):
    from apps.tenants.models import CompanyMembership
    from django.urls import reverse
    client.force_login(data["user"])
    for name in ["finance_home", "cheque_list", "recurring_list", "asset_list"]:
        assert client.get(reverse(f"webapp:{name}")).status_code == 200
    resp = client.post(reverse("webapp:cheque_list"), {"direction": "received", "customer": data["customer"].id,
                       "cheque_number": "55", "amount": "120", "cheque_date": "2026-10-10"})
    assert resp.status_code == 302
    cheque = tenant_a.postdatedcheque_set.get() if hasattr(tenant_a, "postdatedcheque_set") else None
    from apps.finance.models import PostDatedCheque
    cheque = PostDatedCheque.objects.get(company=tenant_a)
    outsider = CompanyMembership.objects.filter(company=tenant_b).first().user
    client.force_login(outsider)
    client.post(reverse("webapp:cheque_status", args=[cheque.id]), {"status": "cleared"})
    cheque.refresh_from_db()
    assert cheque.status == "pending"  # another company cannot touch it
