from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from apps.accounting.models import Account
from apps.accounting.services import post_journal_entry, seed_chart_of_accounts
from apps.inventory.services import record_stock_movement

from .models import (
    Purchase, PurchaseLine, SupplierPayment, PurchaseReturn, PurchaseReturnLine,
    PurchaseOrder, PurchaseOrderLine, GoodsReceiptNote, GoodsReceiptNoteLine,
)


@transaction.atomic
def create_purchase(*, company, user, supplier, date, lines, warehouse, bill_number="", tax_rate=Decimal("0"), due_date=None,
                    currency=None, exchange_rate=None):
    """Mirror of sales.services.create_invoice — same atomic three-step pattern,
    opposite accounts (Dr Inventory/Expense, Cr Accounts Payable).

    Phase 30: `due_date` defaults from the supplier's `payment_terms_days`
    when not given explicitly, same as sales.services.create_invoice."""
    if not lines:
        raise ValidationError("Purchase must have at least one line.")

    if due_date is None:
        from datetime import timedelta, date as _date
        purchase_date = date if isinstance(date, _date) else parse_date(str(date))
        due_date = purchase_date + timedelta(days=supplier.payment_terms_days)

    from apps.sales.services import exchange_rate_for
    currency = (currency or company.default_currency).upper()
    rate = Decimal(exchange_rate) if exchange_rate is not None else exchange_rate_for(company=company, currency=currency, date=date)
    from apps.sales.services import calculate_tax
    computed_lines = []
    uses_tax_codes = any(l.get("tax_code") is not None for l in lines)
    for line in lines:
        amount = Decimal(line["quantity"]) * Decimal(line["unit_cost"])
        taxable, line_tax = calculate_tax(amount=amount, tax_code=line.get("tax_code"), date=date)
        computed_lines.append((line, taxable, line_tax))
    transaction_subtotal = sum((x[1] for x in computed_lines), Decimal("0"))
    transaction_tax = (sum((x[2] for x in computed_lines), Decimal("0")) if uses_tax_codes
                       else (transaction_subtotal * tax_rate).quantize(Decimal("0.01")))
    transaction_total = transaction_subtotal + transaction_tax
    subtotal = (transaction_subtotal * rate).quantize(Decimal("0.01"))
    tax_amount = (transaction_tax * rate).quantize(Decimal("0.01"))
    total = (transaction_total * rate).quantize(Decimal("0.01"))

    purchase = Purchase.objects.create(
        company=company, supplier=supplier, bill_number=bill_number,
        date=date, due_date=due_date, subtotal=subtotal, tax_amount=tax_amount, total=total,
        currency=currency, exchange_rate=rate, transaction_subtotal=transaction_subtotal,
        transaction_tax_amount=transaction_tax, transaction_total=transaction_total,
        tax_breakdown={
            code: str(sum((tax for line, _, tax in computed_lines if line.get("tax_code") and line["tax_code"].code == code), Decimal("0")))
            for code in {line["tax_code"].code for line, _, _ in computed_lines if line.get("tax_code")}
        },
    )

    PurchaseLine.objects.bulk_create([
        PurchaseLine(
            purchase=purchase, product=l["product"], quantity=l["quantity"],
            unit_cost=l["unit_cost"], line_total=Decimal(l["quantity"]) * Decimal(l["unit_cost"]),
            tax_code=l.get("tax_code"), taxable_amount=taxable, tax_amount=line_tax,
        )
        for l, taxable, line_tax in computed_lines
    ])

    for l in lines:
        record_stock_movement(
            company=company, product=l["product"], warehouse=warehouse,
            quantity=Decimal(l["quantity"]), reason="purchase", reference=bill_number or f"PUR#{purchase.id}",
        )

    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["1200", "2000", "2100"])}
    je_lines = [
        (accounts["1200"], total, Decimal("0")),           # Dr Inventory
        (accounts["2000"], Decimal("0"), subtotal),         # Cr Accounts Payable
    ]
    if tax_amount:
        je_lines.append((accounts["2100"], Decimal("0"), tax_amount))

    entry = post_journal_entry(
        company=company, date=date, lines=je_lines, user=user,
        reference=bill_number or f"PUR#{purchase.id}", source_type="purchase", source_id=purchase.id,
    )
    purchase.journal_entry = entry
    purchase.save(update_fields=["journal_entry"])

    return purchase


@transaction.atomic
def record_supplier_payment(*, company, user, supplier, amount, date, purchase=None, method="cash"):
    payment = SupplierPayment.objects.create(
        company=company, supplier=supplier, purchase=purchase, amount=amount, date=date, method=method,
    )
    # Cash payments leave the cash box; bank, card and cheque payments leave the bank.
    asset_code = "1000" if method == "cash" else "1010"
    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=[asset_code, "2000"])}
    entry = post_journal_entry(
        company=company, date=date, user=user,
        lines=[(accounts["2000"], amount, Decimal("0")), (accounts[asset_code], Decimal("0"), amount)],
        reference=f"SupPayment#{payment.id}", source_type="supplier_payment", source_id=payment.id,
    )
    payment.journal_entry = entry
    payment.save(update_fields=["journal_entry"])

    if purchase:
        purchase.amount_paid = purchase.amount_paid + amount
        purchase.status = "paid" if purchase.amount_paid >= purchase.total else "partial"
        purchase.save(update_fields=["amount_paid", "status"])

    return payment


@transaction.atomic
def process_purchase_return(*, company, user, purchase, date, lines, warehouse, reason="", refund_method="supplier_credit"):
    """
    Phase 27 (part 2) — mirror of sales.services.process_return, opposite
    direction: goods go back OUT of stock (negative movement, reason
    "purchase_return") and the reversal is Dr AP-or-Cash / Cr Inventory
    instead of Dr Sales Revenue / Cr AR-or-Cash. Like the sales side, tax
    is intentionally not decomposed out of `total` here — same accepted
    simplification documented on sales.services.process_return.

    lines: [{"product": Product, "quantity": Decimal, "unit_cost": Decimal}, ...]
    """
    if not lines:
        raise ValidationError("Purchase return must have at least one line.")

    total = sum((Decimal(l["quantity"]) * Decimal(l["unit_cost"]) for l in lines), Decimal("0"))

    purchase_return = PurchaseReturn.objects.create(
        company=company, purchase=purchase, date=date, reason=reason, total=total, refund_method=refund_method,
    )
    PurchaseReturnLine.objects.bulk_create([
        PurchaseReturnLine(
            purchase_return=purchase_return, product=l["product"], quantity=l["quantity"],
            unit_cost=l["unit_cost"], line_total=Decimal(l["quantity"]) * Decimal(l["unit_cost"]),
        )
        for l in lines
    ])

    for l in lines:
        if l["product"].is_stock_tracked:
            record_stock_movement(
                company=company, product=l["product"], warehouse=warehouse,
                quantity=-Decimal(l["quantity"]), reason="purchase_return", reference=f"PRET#{purchase_return.id}",
            )

    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["1000", "1200", "2000"])}
    if refund_method == "supplier_credit":
        je_lines = [
            (accounts["2000"], total, Decimal("0")),   # Dr Accounts Payable (reduces what we owe the supplier)
            (accounts["1200"], Decimal("0"), total),   # Cr Inventory (goods leaving stock)
        ]
    else:
        je_lines = [
            (accounts["1000"], total, Decimal("0")),   # Dr Cash (refund received from supplier)
            (accounts["1200"], Decimal("0"), total),   # Cr Inventory (goods leaving stock)
        ]

    entry = post_journal_entry(
        company=company, date=date, lines=je_lines, user=user,
        reference=f"PRET#{purchase_return.id}", source_type="purchase_return", source_id=purchase_return.id,
    )
    purchase_return.journal_entry = entry
    purchase_return.save(update_fields=["journal_entry"])

    return purchase_return


# ================================================================
# Phase 32 — Purchase Order → Goods Receipt → Supplier Bill Workflow
# ================================================================
#
# Deliberately a SEPARATE flow from create_purchase() above, which stays
# exactly as it was — the direct "cash and carry" bill-with-no-PO path
# many small businesses use. This adds the fuller procurement path for
# businesses that want PO approval + partial receiving + a bill matched
# against what was actually received, without breaking the simple path
# or its existing callers.


@transaction.atomic
def create_purchase_order(*, company, user, supplier, date, lines, reference=""):
    """
    lines: [{"product": Product, "quantity": Decimal, "unit_cost": Decimal}, ...]
    No accounting entry, no stock movement — a PO is a request, not a
    financial or inventory event (acceptance criteria: "PO does not
    change ledger").
    """
    if not lines:
        raise ValidationError("Purchase order must have at least one line.")
    if supplier.company_id != company.id:
        raise ValidationError("This supplier does not belong to the active company.")

    po = PurchaseOrder.objects.create(
        company=company, supplier=supplier, date=date, reference=reference, created_by=user,
    )
    PurchaseOrderLine.objects.bulk_create([
        PurchaseOrderLine(
            purchase_order=po, product=l["product"], quantity=l["quantity"], unit_cost=l["unit_cost"],
            line_total=Decimal(l["quantity"]) * Decimal(l["unit_cost"]),
        )
        for l in lines
    ])
    return po


def confirm_purchase_order(*, company, purchase_order):
    """Approval gate: goods can only be received against a confirmed PO,
    never a draft one — a business can review/edit a draft freely."""
    if purchase_order.company_id != company.id:
        raise ValidationError("This purchase order does not belong to the active company.")
    if purchase_order.status != "draft":
        raise ValidationError(f"Cannot confirm a purchase order in '{purchase_order.status}' status.")
    purchase_order.status = "confirmed"
    purchase_order.save(update_fields=["status"])
    return purchase_order


def cancel_purchase_order(*, company, purchase_order):
    if purchase_order.company_id != company.id:
        raise ValidationError("This purchase order does not belong to the active company.")
    if purchase_order.status in ("received",):
        raise ValidationError("Cannot cancel a fully received purchase order.")
    purchase_order.status = "cancelled"
    purchase_order.save(update_fields=["status"])
    return purchase_order


def received_quantity(po_line):
    """Live from GRN lines — never a stored counter, same ledger principle
    as everywhere else (Product.current_stock(), account_balance(), ...)."""
    from django.db.models import Sum
    return po_line.receipt_lines.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def billed_quantity(po_line):
    """Live from PurchaseLine rows that reference this PO line."""
    from django.db.models import Sum
    return po_line.billed_lines.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def _refresh_po_status(purchase_order):
    lines = list(purchase_order.lines.all())
    total_ordered = sum((l.quantity for l in lines), Decimal("0"))
    total_received = sum((received_quantity(l) for l in lines), Decimal("0"))
    if total_received <= 0:
        new_status = "confirmed"
    elif total_received >= total_ordered:
        new_status = "received"
    else:
        new_status = "partially_received"
    if purchase_order.status not in ("cancelled",) and purchase_order.status != new_status:
        purchase_order.status = new_status
        purchase_order.save(update_fields=["status"])


@transaction.atomic
def create_goods_receipt(*, company, user, purchase_order, warehouse, date, lines, allow_over_receipt=False):
    """
    lines: [{"po_line": PurchaseOrderLine, "quantity": Decimal}, ...]

    Debits Inventory and credits the GRNI accrual account (2050) — not
    Accounts Payable directly, since the real invoiced amount isn't known
    yet (Phase 32 rule: "use a clearly documented accrued/GRNI account
    rather than fake expenses"). Blocks receiving more than was ordered
    per line unless `allow_over_receipt=True` (a controlled override the
    view layer only grants to a role with purchases.override_receiving_limits).
    """
    if purchase_order.company_id != company.id:
        raise ValidationError("This purchase order does not belong to the active company.")
    if purchase_order.status not in ("confirmed", "partially_received"):
        raise ValidationError(f"Cannot receive against a purchase order in '{purchase_order.status}' status.")
    if warehouse.company_id != company.id:
        raise ValidationError("This warehouse does not belong to the active company.")
    if not lines:
        raise ValidationError("Goods receipt must have at least one line.")

    for l in lines:
        po_line = l["po_line"]
        if po_line.purchase_order_id != purchase_order.id:
            raise ValidationError("A receipt line's po_line does not belong to this purchase order.")
        qty = Decimal(l["quantity"])
        if qty <= 0:
            raise ValidationError("Receipt quantity must be positive.")
        if not allow_over_receipt:
            already = received_quantity(po_line)
            if already + qty > po_line.quantity:
                raise ValidationError(
                    f"Cannot receive {qty} of {po_line.product.name}: only "
                    f"{po_line.quantity - already} remains unreceived on this PO line."
                )

    grn = GoodsReceiptNote.objects.create(
        company=company, purchase_order=purchase_order, warehouse=warehouse, date=date, received_by=user,
    )
    GoodsReceiptNoteLine.objects.bulk_create([
        GoodsReceiptNoteLine(
            grn=grn, po_line=l["po_line"], quantity=l["quantity"], unit_cost=l["po_line"].unit_cost,
            line_total=Decimal(l["quantity"]) * l["po_line"].unit_cost,
        )
        for l in lines
    ])

    for l in lines:
        if l["po_line"].product.is_stock_tracked:
            record_stock_movement(
                company=company, product=l["po_line"].product, warehouse=warehouse,
                quantity=Decimal(l["quantity"]), reason="goods_receipt", reference=f"GRN#{grn.id}",
            )

    seed_chart_of_accounts(company)  # defensive — guarantees 2050 exists even for pre-Phase-32 companies
    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["1200", "2050"])}
    total = sum((Decimal(l["quantity"]) * l["po_line"].unit_cost for l in lines), Decimal("0"))
    if total > 0:
        entry = post_journal_entry(
            company=company, date=date, user=user,
            lines=[(accounts["1200"], total, Decimal("0")), (accounts["2050"], Decimal("0"), total)],
            reference=f"GRN#{grn.id}", source_type="goods_receipt", source_id=grn.id,
        )
        grn.journal_entry = entry
        grn.save(update_fields=["journal_entry"])

    _refresh_po_status(purchase_order)
    return grn


@transaction.atomic
def create_bill_from_grn(*, company, user, purchase_order, lines, bill_number="", date, tax_rate=Decimal("0"), allow_over_billing=False):
    """
    lines: [{"po_line": PurchaseOrderLine, "quantity": Decimal, "unit_cost": Decimal (optional override)}, ...]

    Posts the final accounting liability (Phase 32 rule: "supplier bill
    posts the final accounting liability") — reverses the GRNI accrual
    for the billed quantity and raises the real Accounts Payable. Does
    NOT touch stock or Inventory again; that already happened at GRN
    time. Blocks billing more than was received-and-not-yet-billed per
    line unless `allow_over_billing=True`.
    """
    if purchase_order.company_id != company.id:
        raise ValidationError("This purchase order does not belong to the active company.")
    if not lines:
        raise ValidationError("Bill must have at least one line.")

    for l in lines:
        po_line = l["po_line"]
        if po_line.purchase_order_id != purchase_order.id:
            raise ValidationError("A bill line's po_line does not belong to this purchase order.")
        qty = Decimal(l["quantity"])
        if qty <= 0:
            raise ValidationError("Bill quantity must be positive.")
        if not allow_over_billing:
            available = received_quantity(po_line) - billed_quantity(po_line)
            if qty > available:
                raise ValidationError(
                    f"Cannot bill {qty} of {po_line.product.name}: only {available} received-but-unbilled "
                    f"on this PO line."
                )

    resolved = [
        {"po_line": l["po_line"], "quantity": Decimal(l["quantity"]), "unit_cost": Decimal(l.get("unit_cost", l["po_line"].unit_cost))}
        for l in lines
    ]
    subtotal = sum((l["quantity"] * l["unit_cost"] for l in resolved), Decimal("0"))
    tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
    total = subtotal + tax_amount

    purchase = Purchase.objects.create(
        company=company, purchase_order=purchase_order, supplier=purchase_order.supplier,
        bill_number=bill_number, date=date, subtotal=subtotal, tax_amount=tax_amount, total=total,
    )
    PurchaseLine.objects.bulk_create([
        PurchaseLine(
            purchase=purchase, product=l["po_line"].product, quantity=l["quantity"], unit_cost=l["unit_cost"],
            line_total=l["quantity"] * l["unit_cost"], po_line=l["po_line"],
        )
        for l in resolved
    ])

    seed_chart_of_accounts(company)
    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["2000", "2050", "2100"])}
    # Mirrors create_purchase()'s existing tax convention: the debit side
    # (there, Inventory; here, GRNI) absorbs the full total including tax,
    # while Accounts Payable and Tax Payable split the credit side. Kept
    # consistent with the rest of the codebase rather than introducing a
    # different tax model just for this flow — full input-tax handling is
    # Phase 37's job (Configurable Tax Engine).
    je_lines = [
        (accounts["2050"], total, Decimal("0")),              # Dr GRNI — reverses the receipt-time accrual
        (accounts["2000"], Decimal("0"), subtotal),            # Cr Accounts Payable
    ]
    if tax_amount:
        je_lines.append((accounts["2100"], Decimal("0"), tax_amount))  # Cr Tax Payable

    entry = post_journal_entry(
        company=company, date=date, lines=je_lines, user=user,
        reference=bill_number or f"BILL#{purchase.id}", source_type="purchase", source_id=purchase.id,
    )
    purchase.journal_entry = entry
    purchase.save(update_fields=["journal_entry"])
    return purchase
