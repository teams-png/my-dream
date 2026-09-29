"""
Phase 26: closes the invoice-linkage TODO. Same shape as mobile_shop
(Phase 26) and gym/spa (Phase 22/23) — sell_unit() invoices via
sales.services.create_invoice() before marking the unit sold.
ServiceTicket completion (start_service/complete_service/deliver_service)
intentionally does NOT invoice yet — a repair job's pricing/line-item
convention (labour vs. parts) hasn't been settled, same open question as
textile's tailoring orders; left for its own phase.

Known accepted quirk (same as mobile_shop's, PHASE24_NOTES.md class): a
StockMovement gets written if this Product is is_stock_tracked, which
doesn't reflect real warehouse quantity the way CycleUnit.status does per
unit. Same per-company data decision, not forced here.
"""
from decimal import Decimal

from django.db import transaction

from apps.customers.services import get_or_create_walkin_customer
from apps.sales.services import create_invoice


@transaction.atomic
def sell_unit(unit, *, company, user, warehouse, sold_price, sold_date, buyer=None):
    if unit.status != "in_stock":
        raise ValueError(f"Unit {unit.serial_number} is not in stock (status: {unit.status}).")

    invoice_customer = buyer or get_or_create_walkin_customer(company)
    create_invoice(
        company=company, user=user, customer=invoice_customer, date=sold_date, warehouse=warehouse,
        lines=[{"product": unit.product, "quantity": Decimal("1"), "unit_price": sold_price}],
    )

    unit.status = "sold"
    unit.buyer = buyer
    unit.sold_price = sold_price
    unit.sold_date = sold_date
    unit.save(update_fields=["status", "buyer", "sold_price", "sold_date"])
    return unit


@transaction.atomic
def return_unit(unit):
    if unit.status != "sold":
        raise ValueError(f"Unit {unit.serial_number} was not sold, cannot be returned.")
    unit.status = "in_stock"
    unit.buyer = None
    unit.sold_price = None
    unit.sold_date = None
    unit.save(update_fields=["status", "buyer", "sold_price", "sold_date"])
    return unit


def start_service(ticket):
    if ticket.status != "received":
        raise ValueError(f"Ticket is '{ticket.status}', cannot start.")
    ticket.status = "in_progress"
    ticket.save(update_fields=["status"])
    return ticket


def complete_service(ticket, *, cost):
    if ticket.status != "in_progress":
        raise ValueError(f"Ticket is '{ticket.status}', cannot complete.")
    ticket.status = "completed"
    ticket.cost = cost
    ticket.save(update_fields=["status", "cost"])
    return ticket


def deliver_service(ticket, *, delivered_date):
    if ticket.status != "completed":
        raise ValueError(f"Ticket is '{ticket.status}', cannot deliver.")
    ticket.status = "delivered"
    ticket.delivered_date = delivered_date
    ticket.save(update_fields=["status", "delivered_date"])
    return ticket
