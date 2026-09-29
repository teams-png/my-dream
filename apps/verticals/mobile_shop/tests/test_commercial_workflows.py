from decimal import Decimal
from django.utils import timezone
import pytest

from apps.inventory.models import Product
from apps.verticals.mobile_shop.models import MobileRepairJob, MobileTradeIn, MobileUnit
from apps.verticals.mobile_shop.services import create_repair_job, complete_repair_job, accept_trade_in

pytestmark = pytest.mark.django_db


def test_repair_completion_creates_shared_invoice(tenant_a, tenant_a_owner, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="REPAIR-SERVICE", stock_price=Decimal("80"))
    f["product"].is_stock_tracked = False
    f["product"].tracking_type = "none"
    f["product"].save(update_fields=["is_stock_tracked", "tracking_type"])
    job = create_repair_job(
        company=tenant_a, customer=f["customer"], warehouse=f["warehouse"],
        device_description="Phone", reported_issue="Screen issue", service_product=f["product"],
    )
    completed = complete_repair_job(
        company=tenant_a, user=tenant_a_owner, job=job, date=timezone.localdate(),
        final_cost=Decimal("80"), work_done="Service completed",
    )
    assert completed.status == "completed"
    assert completed.invoice.total == Decimal("80")


def test_trade_in_creates_purchase_and_imei_stock(tenant_a, tenant_a_owner, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="USED-PHONE", stock_price=Decimal("300"))
    trade = MobileTradeIn.objects.create(
        company=tenant_a, customer=f["customer"], product=f["product"], imei="990000000000001",
        condition="used", quoted_value=Decimal("200"), warehouse=f["warehouse"],
    )
    accepted = accept_trade_in(company=tenant_a, user=tenant_a_owner, trade_in=trade, date=timezone.localdate())
    assert accepted.status == "accepted"
    assert accepted.purchase.total == Decimal("200")
    assert accepted.mobile_unit.status == "in_stock"
