"""
Phase 26: closes the invoice-linkage TODO left since this file was first
written. Same shape as gym/spa (Phase 22/23): sell_unit() now invoices via
sales.services.create_invoice() before marking the unit sold, so the sale
always has a real ledger entry behind it — never a bare status flip. The
IMEI-level status stays the source of truth for whether a specific phone
is in stock (see the model docstring); the invoice call is only there so
the sale shows up in accounting/reports too.

Known accepted quirk (same class as gym/spa's, PHASE24_NOTES.md): if this
Product is marked is_stock_tracked, create_invoice() also writes a
StockMovement for it — which double-counts against MobileUnit.status
rather than reflecting real warehouse quantity, since a mobile shop's unit
of stock is one IMEI, not a Product-level count (see the model docstring).
Left as a per-company data decision (mark the linked Product
is_stock_tracked=False if this bothers your reports) rather than forced
here, since some shops may deliberately also track these Products through
the generic Purchase flow.
"""
from decimal import Decimal

from django.db import transaction

from apps.customers.services import get_or_create_walkin_customer
from apps.sales.services import create_invoice
from apps.tenants.services import next_counter_value


@transaction.atomic
def sell_unit(unit, *, company, user, warehouse, sold_price, sold_date, buyer=None):
    if unit.status != "in_stock":
        raise ValueError(f"Unit {unit.imei} is not in stock (status: {unit.status}).")

    invoice_customer = buyer or get_or_create_walkin_customer(company)
    invoice = create_invoice(
        company=company, user=user, customer=invoice_customer, date=sold_date, warehouse=warehouse,
        lines=[{"product": unit.product, "quantity": Decimal("1"), "unit_price": sold_price}],
    )

    unit.status = "sold"
    unit.buyer = buyer
    unit.sold_price = sold_price
    unit.sold_date = sold_date
    unit.sale_invoice = invoice
    unit.warehouse = warehouse
    unit.save(update_fields=["status", "buyer", "sold_price", "sold_date", "sale_invoice", "warehouse"])
    return unit


@transaction.atomic
def return_unit(unit, *, company=None, user=None, date=None, refund_method="cash"):
    """Return a handset through the shared credit/return engine when an invoice exists."""
    if unit.status != "sold":
        raise ValueError(f"Unit {unit.imei} was not sold, cannot be returned.")

    if unit.sale_invoice_id:
        if not all((company, user, date, unit.warehouse_id)):
            raise ValueError("Company, user, return date and original warehouse are required.")
        from apps.sales.services import process_return
        process_return(
            company=company, user=user, invoice=unit.sale_invoice, date=date, warehouse=unit.warehouse,
            refund_method=refund_method, reason=f"Mobile return IMEI {unit.imei}",
            lines=[{"product": unit.product, "quantity": Decimal("1"), "unit_price": unit.sold_price}],
        )
    unit.status = "returned"
    unit.buyer = None
    unit.sold_price = None
    unit.sold_date = None
    unit.save(update_fields=["status", "buyer", "sold_price", "sold_date"])
    return unit


def send_for_repair(unit):
    unit.status = "under_repair"
    unit.save(update_fields=["status"])
    return unit


def restock_after_repair(unit):
    unit.status = "in_stock"
    unit.save(update_fields=["status"])
    return unit


@transaction.atomic
def create_repair_job(*, company, customer, warehouse, device_description, reported_issue,
                      mobile_unit=None, imei="", estimated_cost=Decimal("0"), service_product=None):
    from .models import MobileRepairJob
    if customer.company_id != company.id or warehouse.company_id != company.id:
        raise ValueError("Customer or branch does not belong to the active company.")
    if mobile_unit and mobile_unit.company_id != company.id:
        raise ValueError("Mobile unit does not belong to the active company.")
    number = f"REP-{next_counter_value(company, 'mobile_repair'):06d}"
    return MobileRepairJob.objects.create(
        company=company, job_number=number, customer=customer, warehouse=warehouse,
        mobile_unit=mobile_unit, imei=imei or (mobile_unit.imei if mobile_unit else ""),
        device_description=device_description, reported_issue=reported_issue,
        estimated_cost=estimated_cost, service_product=service_product,
    )


@transaction.atomic
def complete_repair_job(*, company, user, job, date, final_cost, work_done=""):
    from django.utils import timezone
    job = job.__class__.objects.select_for_update().get(company=company, pk=job.pk)
    if job.status in {"completed", "cancelled"}:
        raise ValueError("This repair job cannot be completed.")
    cost = Decimal(final_cost)
    if cost < 0:
        raise ValueError("Final cost cannot be negative.")
    invoice = None
    if cost:
        if not job.service_product_id or job.service_product.is_stock_tracked:
            raise ValueError("A non-stock service product is required before invoicing the repair.")
        invoice = create_invoice(
            company=company, user=user, customer=job.customer, date=date, warehouse=job.warehouse,
            lines=[{"product": job.service_product, "quantity": Decimal("1"), "unit_price": cost}],
        )
    job.final_cost = cost
    job.work_done = work_done
    job.invoice = invoice
    job.status = "completed"
    job.completed_at = timezone.now()
    job.save(update_fields=["final_cost", "work_done", "invoice", "status", "completed_at"])
    return job


@transaction.atomic
def record_installment_payment(*, company, user, plan, amount, date, method="cash"):
    from .models import MobileInstallmentPayment
    if plan.company_id != company.id or plan.status not in {"active", "overdue"}:
        raise ValueError("This installment plan cannot receive payments.")
    amount = Decimal(amount)
    if amount <= 0 or amount > plan.outstanding:
        raise ValueError("Payment must be positive and cannot exceed the outstanding balance.")
    payment = __import__("apps.sales.services", fromlist=["record_customer_payment"]).record_customer_payment(
        company=company, user=user, customer=plan.customer, invoice=plan.invoice,
        amount=amount, date=date, method=method,
    )
    row = MobileInstallmentPayment.objects.create(
        company=company, plan=plan, amount=amount, date=date, method=method, customer_payment=payment,
    )
    if plan.outstanding <= 0:
        plan.status = "paid"
        plan.save(update_fields=["status"])
    return row


@transaction.atomic
def accept_trade_in(*, company, user, trade_in, date):
    from apps.suppliers.models import Supplier
    from apps.purchases.services import create_purchase
    from .models import MobileUnit
    trade_in = trade_in.__class__.objects.select_for_update().get(company=company, pk=trade_in.pk)
    if trade_in.status != "quoted":
        raise ValueError("Trade-in has already been resolved.")
    value = trade_in.accepted_value or trade_in.quoted_value
    supplier, _ = Supplier.objects.get_or_create(
        company=company, name=f"Trade-in customer: {trade_in.customer.name}",
        defaults={"phone": trade_in.customer.phone, "email": trade_in.customer.email},
    )
    purchase = create_purchase(
        company=company, user=user, supplier=supplier, date=date, warehouse=trade_in.warehouse,
        bill_number=f"TRD-{trade_in.id}", lines=[{"product": trade_in.product, "quantity": Decimal("1"), "unit_cost": value}],
    )
    unit = MobileUnit.objects.create(
        company=company, product=trade_in.product, imei=trade_in.imei, serial_number=trade_in.serial_number,
        condition=trade_in.condition, purchase_price=value, status="in_stock", warehouse=trade_in.warehouse,
    )
    trade_in.status = "accepted"
    trade_in.accepted_value = value
    trade_in.purchase = purchase
    trade_in.mobile_unit = unit
    trade_in.save(update_fields=["status", "accepted_value", "purchase", "mobile_unit"])
    return trade_in
