"""
sales.services — invoice creation is the reference implementation of the
"one service call, one atomic transaction, three side effects" pattern
(Phase 0 Section 1 / Phase 1 Section 8): create the invoice row, write the
stock movement, post the journal entry. All three succeed or none do.
"""
from decimal import Decimal
from django.db import transaction, models
from django.db.models import Sum
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from apps.accounting.models import Account
from apps.accounting.services import post_journal_entry
from apps.inventory.services import record_stock_movement, sell_batch_stock, sell_serial_stock, restore_serial_stock

from .models import (
    SalesInvoice, SalesInvoiceLine, CustomerPayment, SalesReturn, SalesReturnLine, Coupon,
    Quotation, QuotationLine, SalesOrder, SalesOrderLine, DeliveryNote, DeliveryLine,
    POSShift, POSCashMovement, POSCart, POSCartLine, POSReceipt, POSPayment,
    CommercialSettings, PriceListItem, Promotion,
    ExchangeRate,
    TaxCode,
)


MONEY = Decimal("0.01")


def exchange_rate_for(*, company, currency, date):
    currency = currency.upper()
    if currency == company.default_currency.upper():
        return Decimal("1")
    row = ExchangeRate.objects.for_company(company).filter(
        currency=currency, effective_date__lte=date
    ).order_by("-effective_date").first()
    if row is None or row.rate <= 0:
        raise ValidationError(f"No exchange rate is configured for {currency} on {date}.")
    return row.rate


def calculate_tax(*, amount, tax_code, date):
    amount = Decimal(amount)
    if tax_code is None:
        return amount.quantize(MONEY), Decimal("0")
    if (not tax_code.is_active or tax_code.effective_from > date or
            (tax_code.effective_to and tax_code.effective_to < date)):
        raise ValidationError("Tax code is not effective on the document date.")
    if tax_code.classification != "taxable" or tax_code.rate == 0:
        return amount.quantize(MONEY), Decimal("0")
    rate = tax_code.rate / Decimal("100")
    if tax_code.inclusive:
        taxable = (amount / (Decimal("1") + rate)).quantize(MONEY)
        return taxable, amount.quantize(MONEY) - taxable
    taxable = amount.quantize(MONEY)
    return taxable, (taxable * rate).quantize(MONEY)


def _next_invoice_number(company):
    """Race-safe per-company sequence — see tenants.models.CompanyCounter /
    tenants.services.next_counter_value for the locking implementation.
    Must be called from inside create_invoice's own @transaction.atomic
    (it is, below) so the counter row lock covers the whole invoice write."""
    from apps.tenants.services import next_counter_value

    n = next_counter_value(company, "sales_invoice")
    return f"INV-{n:06d}"


@transaction.atomic
def create_invoice(*, company, user, customer, date, lines, warehouse, due_date=None, tax_rate=Decimal("0"),
                    discount_amount=Decimal("0"), coupon_code="", discount_reason="",
                    discount_approved_by=None, currency=None, exchange_rate=None):
    """
    lines: list of dicts [{"product": Product, "quantity": Decimal, "unit_price": Decimal}, ...]

    Phase 30: if `due_date` isn't given explicitly, it's computed from the
    customer's `payment_terms_days` (default 30) — so ageing/collections
    always has a due date to work from without every caller having to know
    about payment terms.
    """
    if not lines:
        raise ValidationError("Invoice must have at least one line.")

    if due_date is None:
        from datetime import timedelta, date as _date
        invoice_date = date if isinstance(date, _date) else parse_date(str(date))
        due_date = invoice_date + timedelta(days=customer.payment_terms_days)

    currency = (currency or company.default_currency).upper()
    rate = Decimal(exchange_rate) if exchange_rate is not None else exchange_rate_for(
        company=company, currency=currency, date=date,
    )
    if rate <= 0:
        raise ValidationError("Exchange rate must be positive.")
    computed_lines = []
    uses_tax_codes = any(l.get("tax_code") is not None for l in lines)
    for line in lines:
        gross_or_net = Decimal(line["quantity"]) * Decimal(line["unit_price"])
        taxable, line_tax = calculate_tax(amount=gross_or_net, tax_code=line.get("tax_code"), date=date)
        computed_lines.append((line, taxable, line_tax))
    transaction_subtotal = sum((x[1] for x in computed_lines), Decimal("0"))
    discount_amount = Decimal(discount_amount)
    if discount_amount < 0 or discount_amount > transaction_subtotal:
        raise ValidationError("Discount must be between zero and the invoice subtotal.")
    settings, _ = CommercialSettings.objects.get_or_create(company=company)
    discount_percent = (discount_amount * Decimal("100") / transaction_subtotal) if transaction_subtotal else Decimal("0")
    if coupon_code and not discount_reason.strip():
        discount_reason = f"Coupon {coupon_code}"
    if discount_amount and not discount_reason.strip():
        raise ValidationError("A discount reason is required.")
    if (discount_percent > settings.discount_approval_threshold_percent and
            discount_approved_by is None and not coupon_code):
        raise ValidationError("This discount exceeds the approval threshold.")
    transaction_tax = (sum((x[2] for x in computed_lines), Decimal("0")) if uses_tax_codes
                       else (transaction_subtotal * tax_rate).quantize(MONEY))
    transaction_total = transaction_subtotal + transaction_tax - discount_amount
    subtotal = (transaction_subtotal * rate).quantize(MONEY)
    tax_amount = (transaction_tax * rate).quantize(MONEY)
    base_discount = (discount_amount * rate).quantize(MONEY)
    total = (transaction_total * rate).quantize(MONEY)

    invoice = SalesInvoice.objects.create(
        company=company, customer=customer, invoice_number=_next_invoice_number(company),
        date=date, due_date=due_date, subtotal=subtotal, discount_amount=base_discount,
        tax_amount=tax_amount, total=total, coupon_code=coupon_code, warehouse=warehouse,
        discount_reason=discount_reason, discount_approved_by=discount_approved_by,
        currency=currency, exchange_rate=rate, transaction_subtotal=transaction_subtotal,
        transaction_tax_amount=transaction_tax, transaction_total=transaction_total,
        tax_breakdown={
            code: str(sum((tax for line, _, tax in computed_lines if line.get("tax_code") and line["tax_code"].code == code), Decimal("0")))
            for code in {line["tax_code"].code for line, _, _ in computed_lines if line.get("tax_code")}
        },
    )

    SalesInvoiceLine.objects.bulk_create([
        SalesInvoiceLine(
            invoice=invoice, product=l["product"], quantity=l["quantity"],
            unit_price=l["unit_price"], line_total=Decimal(l["quantity"]) * Decimal(l["unit_price"]),
            batch=l.get("batch"), serial=l.get("serial"), so_line=l.get("so_line"),
            tax_code=l.get("tax_code"), taxable_amount=taxable, tax_amount=line_tax,
        )
        for l, taxable, line_tax in computed_lines
    ])

    for l in lines:
        product = l["product"]
        if not product.is_stock_tracked:
            continue
        if l.get("so_line") is not None:
            # Phase 33: this line bills a SalesOrderLine that was already
            # delivered — stock left at delivery time. Moving it again
            # here would be the double-decrement the acceptance criteria
            # explicitly forbids.
            continue
        if product.tracking_type == "batch" and l.get("batch") is not None:
            sell_batch_stock(
                company=company, product=product, warehouse=warehouse, batch=l["batch"],
                quantity=l["quantity"], reference=invoice.invoice_number,
            )
        elif product.tracking_type == "serial" and l.get("serial") is not None:
            sell_serial_stock(
                company=company, product=product, serial=l["serial"], reference=invoice.invoice_number,
            )
        else:
            record_stock_movement(
                company=company, product=product, warehouse=warehouse,
                quantity=-Decimal(l["quantity"]), reason="sale", reference=invoice.invoice_number,
            )

    accounts = {a.code: a for a in Account.objects.for_company(company).filter(
        code__in=["1100", "4000", "2100"]
    )}
    je_lines = [
        (accounts["1100"], total, Decimal("0")),          # Dr Accounts Receivable (net of discount)
        (accounts["4000"], Decimal("0"), subtotal),        # Cr Sales Revenue (base currency)
    ]
    if base_discount:
        je_lines.append((accounts["4000"], base_discount, Decimal("0")))
    if tax_amount:
        je_lines.append((accounts["2100"], Decimal("0"), tax_amount))  # Cr Tax Payable

    entry = post_journal_entry(
        company=company, date=date, lines=je_lines, user=user,
        reference=invoice.invoice_number, source_type="sales_invoice", source_id=invoice.id,
    )
    invoice.journal_entry = entry
    invoice.save(update_fields=["journal_entry"])

    return invoice


def validate_coupon(*, company, code, subtotal, date):
    """Returns (coupon, discount_amount) if valid, else raises ValidationError."""
    coupon = Coupon.objects.for_company(company).filter(code__iexact=code.strip()).first()
    if not coupon or not coupon.is_active:
        raise ValidationError("Invalid or inactive coupon code.")
    if date < coupon.start_date or date > coupon.expiry_date:
        raise ValidationError("This coupon isn't valid on this date.")
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        raise ValidationError("This coupon has reached its usage limit.")
    if subtotal < coupon.min_purchase:
        raise ValidationError(f"Minimum purchase of {coupon.min_purchase} required for this coupon.")

    if coupon.discount_type == "percentage":
        discount = (subtotal * coupon.discount_value / Decimal("100"))
    else:
        discount = coupon.discount_value
    if coupon.max_discount:
        discount = min(discount, coupon.max_discount)
    discount = min(discount, subtotal)
    return coupon, discount.quantize(Decimal("0.01"))


def redeem_coupon_usage(coupon):
    coupon.times_used += 1
    coupon.save(update_fields=["times_used"])


def resolve_commercial_price(*, company, customer, product, date):
    """Deterministic precedence: customer price list, general price list,
    product selling price; then the single highest-priority active promotion.
    Stable id ordering breaks equal-priority ties."""
    eligible = PriceListItem.objects.filter(
        price_list__company=company, price_list__is_active=True, product=product,
    ).filter(
        models.Q(price_list__start_date__isnull=True) | models.Q(price_list__start_date__lte=date),
        models.Q(price_list__end_date__isnull=True) | models.Q(price_list__end_date__gte=date),
    )
    customer_item = eligible.filter(price_list__customer=customer).order_by("-price_list__priority", "price_list_id").first()
    general_item = eligible.filter(price_list__customer__isnull=True).order_by("-price_list__priority", "price_list_id").first()
    selected = customer_item or general_item
    price = selected.unit_price if selected else product.selling_price
    source = "customer_price_list" if customer_item else ("price_list" if general_item else "product")

    promotion = Promotion.objects.for_company(company).filter(
        is_active=True, start_date__lte=date, end_date__gte=date,
    ).filter(models.Q(product=product) | models.Q(product__isnull=True)).order_by("-priority", "id").first()
    if promotion:
        if promotion.discount_type == "percentage":
            price -= price * promotion.discount_value / Decimal("100")
        else:
            price -= promotion.discount_value
        price = max(price, Decimal("0"))
        source += "+promotion"
    return price.quantize(Decimal("0.01")), source, promotion


@transaction.atomic
def record_customer_payment(*, company, user, customer, amount, date, invoice=None, method="cash",
                            currency=None, exchange_rate=None):
    currency = (currency or (invoice.currency if invoice else company.default_currency)).upper()
    rate = Decimal(exchange_rate) if exchange_rate is not None else exchange_rate_for(
        company=company, currency=currency, date=date,
    )
    transaction_amount = Decimal(amount)
    base_amount = (transaction_amount * rate).quantize(MONEY)
    payment = CustomerPayment.objects.create(
        company=company, customer=customer, invoice=invoice,
        amount=base_amount, date=date, method=method, currency=currency,
        transaction_amount=transaction_amount, exchange_rate=rate, base_amount=base_amount,
    )

    asset_code = "1000" if method == "cash" else "1010"
    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=[asset_code, "1100"])}
    carrying_amount = base_amount
    gain = loss = Decimal("0")
    if invoice and currency != company.default_currency.upper():
        carrying_amount = (transaction_amount * invoice.exchange_rate).quantize(MONEY)
        difference = base_amount - carrying_amount
        gain = max(difference, Decimal("0"))
        loss = max(-difference, Decimal("0"))
        from apps.accounting.services import seed_chart_of_accounts
        seed_chart_of_accounts(company)
        accounts.update({a.code: a for a in Account.objects.for_company(company).filter(code__in=["4050", "5150"])})
    payment_lines = [(accounts[asset_code], base_amount, Decimal("0")),
                     (accounts["1100"], Decimal("0"), carrying_amount)]
    if gain:
        payment_lines.append((accounts["4050"], Decimal("0"), gain))
    if loss:
        payment_lines.append((accounts["5150"], loss, Decimal("0")))
    entry = post_journal_entry(
        company=company, date=date, user=user,
        lines=payment_lines,
        reference=f"Payment#{payment.id}", source_type="customer_payment", source_id=payment.id,
    )
    payment.journal_entry = entry
    payment.save(update_fields=["journal_entry"])

    if invoice:
        invoice.amount_paid = invoice.amount_paid + carrying_amount
        invoice.transaction_amount_paid += transaction_amount
        invoice.status = "paid" if invoice.transaction_amount_paid >= invoice.transaction_total else "partial"
        invoice.save(update_fields=["amount_paid", "transaction_amount_paid", "status"])

    return payment


# ================================================================
# Phase 34 — POS, deliberately layered on the normal invoice/payment engine
# ================================================================

@transaction.atomic
def open_pos_shift(*, company, user, warehouse, opening_cash=Decimal("0")):
    if warehouse.company_id != company.id:
        raise ValidationError("This warehouse does not belong to the active company.")
    if POSShift.objects.for_company(company).filter(cashier=user, status="open").exists():
        raise ValidationError("This cashier already has an open shift.")
    return POSShift.objects.create(
        company=company, cashier=user, warehouse=warehouse,
        opening_cash=Decimal(opening_cash),
    )


@transaction.atomic
def add_pos_cash_movement(*, company, user, shift, kind, amount, reason):
    if shift.company_id != company.id or shift.status != "open":
        raise ValidationError("Cash movements require an open shift for this company.")
    amount = Decimal(amount)
    if amount <= 0 or kind not in {"cash_in", "cash_out"}:
        raise ValidationError("Cash movement amount and type are invalid.")
    return POSCashMovement.objects.create(
        company=company, shift=shift, kind=kind, amount=amount,
        reason=reason, created_by=user,
    )


def pos_expected_cash(*, company, shift):
    if shift.company_id != company.id:
        raise ValidationError("This shift does not belong to the active company.")
    cash_sales = POSPayment.objects.filter(
        receipt__company=company, receipt__shift=shift, method="cash"
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    cash_in = shift.cash_movements.filter(kind="cash_in").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    cash_out = shift.cash_movements.filter(kind="cash_out").aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return shift.opening_cash + cash_sales + cash_in - cash_out


@transaction.atomic
def close_pos_shift(*, company, user, shift, counted_cash):
    shift = POSShift.objects.select_for_update().get(pk=shift.pk)
    if shift.company_id != company.id or shift.cashier_id != user.id:
        raise ValidationError("This shift does not belong to this cashier.")
    if shift.status != "open":
        raise ValidationError("This shift is already closed.")
    expected = pos_expected_cash(company=company, shift=shift)
    counted = Decimal(counted_cash)
    shift.expected_cash = expected
    shift.counted_cash = counted
    shift.variance = counted - expected
    shift.status = "closed"
    shift.closed_at = timezone.now()
    shift.save(update_fields=["expected_cash", "counted_cash", "variance", "status", "closed_at"])
    return shift


@transaction.atomic
def hold_pos_cart(*, company, user, shift, lines, customer=None, reference=""):
    if shift.company_id != company.id or shift.cashier_id != user.id or shift.status != "open":
        raise ValidationError("An open cashier shift is required.")
    if customer is not None and customer.company_id != company.id:
        raise ValidationError("This customer does not belong to the active company.")
    if not lines:
        raise ValidationError("Cart must have at least one line.")
    cart = POSCart.objects.create(
        company=company, shift=shift, customer=customer, reference=reference,
        created_by=user,
    )
    POSCartLine.objects.bulk_create([
        POSCartLine(cart=cart, product=l["product"], quantity=l["quantity"],
                    unit_price=l["unit_price"], discount_amount=l.get("discount_amount", 0))
        for l in lines
    ])
    return cart


@transaction.atomic
def complete_pos_sale(*, company, user, shift, lines, payments, date, customer=None,
                      cart=None, tax_rate=Decimal("0"), discount_amount=Decimal("0"),
                      discount_reason="", discount_approved_by=None, coupon_code="",
                      loyalty_points=0):
    from apps.customers.services import get_or_create_walkin_customer

    shift = POSShift.objects.select_for_update().get(pk=shift.pk)
    if shift.company_id != company.id or shift.cashier_id != user.id or shift.status != "open":
        raise ValidationError("An open cashier shift is required.")
    if cart is not None:
        if cart.company_id != company.id or cart.shift_id != shift.id or cart.status != "held":
            raise ValidationError("This held cart cannot be resumed in the active shift.")
        if not lines:
            lines = [{"product": x.product, "quantity": x.quantity, "unit_price": x.unit_price}
                     for x in cart.lines.select_related("product")]
        customer = customer or cart.customer
    if not lines:
        raise ValidationError("POS sale must have at least one line.")

    for line in lines:
        product = line["product"]
        if product.company_id != company.id:
            raise ValidationError("A product does not belong to the active company.")
        quantity = Decimal(line["quantity"])
        if quantity <= 0:
            raise ValidationError("Product quantity must be positive.")
        if product.is_stock_tracked and product.current_stock(shift.warehouse) < quantity:
            raise ValidationError(f"Insufficient stock for {product.name}.")

    customer = customer or get_or_create_walkin_customer(company=company)
    priced_lines = []
    for line in lines:
        price, _, _ = resolve_commercial_price(
            company=company, customer=customer, product=line["product"], date=date,
        )
        priced_lines.append({**line, "unit_price": price})
    lines = priced_lines
    subtotal = sum((Decimal(l["quantity"]) * Decimal(l["unit_price"]) for l in lines), Decimal("0"))
    configured_discount = Decimal("0")
    if coupon_code:
        coupon, configured_discount = validate_coupon(
            company=company, code=coupon_code, subtotal=subtotal, date=date,
        )
    loyalty_discount = Decimal("0")
    if loyalty_points:
        from apps.customers.services import redeem_points_for_discount
        loyalty_discount = redeem_points_for_discount(
            company=company, customer=customer, points=loyalty_points,
            date=date, reference=f"POS shift {shift.id}",
        )
    total_discount = Decimal(discount_amount) + configured_discount + loyalty_discount
    reasons = [x for x in [discount_reason, f"Coupon {coupon_code}" if coupon_code else "",
                           f"Loyalty redemption {loyalty_points} points" if loyalty_points else ""] if x]
    invoice = create_invoice(
        company=company, user=user, customer=customer, date=date, lines=lines,
        warehouse=shift.warehouse, tax_rate=Decimal(tax_rate), discount_amount=total_discount,
        coupon_code=coupon_code, discount_reason="; ".join(reasons),
        discount_approved_by=discount_approved_by,
    )
    payment_total = sum((Decimal(p["amount"]) for p in payments), Decimal("0"))
    if payment_total != invoice.total:
        raise ValidationError("POS payments must equal the invoice total exactly.")
    if not payments:
        raise ValidationError("At least one payment is required.")

    from apps.tenants.services import next_counter_value
    receipt = POSReceipt.objects.create(
        company=company, shift=shift, invoice=invoice, cart=cart,
        receipt_number=f"POS-{next_counter_value(company, 'pos_receipt'):06d}",
    )
    for item in payments:
        method = item["method"]
        if method not in {"cash", "card", "bank"}:
            raise ValidationError("Unsupported POS payment method.")
        payment = record_customer_payment(
            company=company, user=user, customer=customer, invoice=invoice,
            amount=Decimal(item["amount"]), date=date, method=method,
        )
        POSPayment.objects.create(receipt=receipt, customer_payment=payment, method=method, amount=payment.amount)

    if coupon_code:
        redeem_coupon_usage(coupon)
    from apps.customers.services import earn_points
    earn_points(company=company, customer=customer, amount_spent=invoice.total,
                date=date, reference=invoice.invoice_number)

    if cart is not None:
        cart.status = "completed"
        cart.completed_at = timezone.now()
        cart.save(update_fields=["status", "completed_at"])
    return receipt


@transaction.atomic
def process_return(*, company, user, invoice, date, lines, warehouse, reason="", refund_method="cash"):
    """
    lines: [{"product": Product, "quantity": Decimal, "unit_price": Decimal,
             "batch": ProductBatch (optional), "serial": ProductSerial (optional)}, ...]
    Adds the returned quantity back to stock, reverses the corresponding sales
    revenue, and books the refund out of cash (or against the customer's
    account for store credit).

    Phase 31: restores stock to the same batch/serial the original sale
    used, "where possible" (spec wording) — if a line doesn't explicitly
    say which batch/serial to restore to, it falls back to whatever the
    matching SalesInvoiceLine for that product on this invoice recorded.
    """
    if not lines:
        raise ValidationError("Return must have at least one line.")

    net_total = sum((Decimal(l["quantity"]) * Decimal(l["unit_price"]) for l in lines), Decimal("0"))
    return_taxes = []
    for l in lines:
        original = invoice.lines.filter(product=l["product"]).first()
        per_unit_tax = (original.tax_amount / original.quantity) if original and original.quantity else Decimal("0")
        return_taxes.append((per_unit_tax * Decimal(l["quantity"])).quantize(MONEY))
    tax_total = sum(return_taxes, Decimal("0"))
    total = net_total + tax_total

    sales_return = SalesReturn.objects.create(
        company=company, invoice=invoice, date=date, reason=reason, total=total, refund_method=refund_method,
    )

    def _resolve_batch_serial(l):
        batch, serial = l.get("batch"), l.get("serial")
        if batch is None and serial is None:
            original_line = invoice.lines.filter(product=l["product"]).exclude(
                batch__isnull=True, serial__isnull=True
            ).first()
            if original_line:
                batch, serial = original_line.batch, original_line.serial
        return batch, serial

    resolved = [(l, *_resolve_batch_serial(l)) for l in lines]

    SalesReturnLine.objects.bulk_create([
        SalesReturnLine(
            sales_return=sales_return, product=l["product"], quantity=l["quantity"],
            unit_price=l["unit_price"], line_total=Decimal(l["quantity"]) * Decimal(l["unit_price"]),
            batch=batch, serial=serial,
            tax_amount=return_taxes[index],
        )
        for index, (l, batch, serial) in enumerate(resolved)
    ])

    for l, batch, serial in resolved:
        product = l["product"]
        if not product.is_stock_tracked:
            continue
        if product.tracking_type == "serial" and serial is not None:
            restore_serial_stock(
                company=company, product=product, serial=serial, warehouse=warehouse,
                reference=f"RET#{sales_return.id}",
            )
        else:
            record_stock_movement(
                company=company, product=product, warehouse=warehouse,
                quantity=Decimal(l["quantity"]), reason="sales_return", reference=f"RET#{sales_return.id}",
                batch=batch,
            )

    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["1000", "1100", "2100", "4000"])}
    if refund_method == "store_credit":
        je_lines = [
            (accounts["4000"], net_total, Decimal("0")),
            (accounts["1100"], Decimal("0"), total),   # Cr Accounts Receivable (credit against future bills)
        ]
    else:
        je_lines = [
            (accounts["4000"], net_total, Decimal("0")),
            (accounts["1000"], Decimal("0"), total),   # Cr Cash (refunded out)
        ]
    if tax_total:
        je_lines.append((accounts["2100"], tax_total, Decimal("0")))

    entry = post_journal_entry(
        company=company, date=date, lines=je_lines, user=user,
        reference=f"RET#{sales_return.id}", source_type="sales_return", source_id=sales_return.id,
    )
    sales_return.journal_entry = entry
    sales_return.save(update_fields=["journal_entry"])

    already_returned = SalesReturn.objects.filter(invoice=invoice).exclude(id=sales_return.id).aggregate(
        t=Sum("total")
    )["t"] or Decimal("0")
    if already_returned + total >= invoice.total:
        invoice.status = "void"
    invoice.save(update_fields=["status"])

    return sales_return


# ================================================================
# Phase 33 — Sales Quotation → Sales Order → Delivery → Invoice Workflow
# ================================================================
#
# A SEPARATE flow alongside create_invoice() above, which stays exactly
# as it was — the direct walk-in/POS-style invoice path many verticals
# already use. This adds the fuller order-to-cash path for businesses
# that quote, confirm an order, deliver, and invoice against what was
# actually delivered — without breaking the simple path or its callers.


@transaction.atomic
def create_quotation(*, company, user, customer, date, lines, notes="", valid_until=None):
    """lines: [{"product": Product, "quantity": Decimal, "unit_price": Decimal}, ...]
    No accounting entry, no stock movement (acceptance criteria: "quotation
    ... does not post accounting entries")."""
    if not lines:
        raise ValidationError("Quotation must have at least one line.")
    if customer.company_id != company.id:
        raise ValidationError("This customer does not belong to the active company.")

    from apps.tenants.services import next_counter_value
    quotation = Quotation.objects.create(company=company, customer=customer, date=date, notes=notes, created_by=user,
                                         valid_until=valid_until,
                                         number=f"QT-{next_counter_value(company, 'quotation'):05d}")
    QuotationLine.objects.bulk_create([
        QuotationLine(
            quotation=quotation, product=l["product"], quantity=l["quantity"], unit_price=l["unit_price"],
            line_total=Decimal(l["quantity"]) * Decimal(l["unit_price"]),
        )
        for l in lines
    ])
    return quotation


def send_quotation(*, company, quotation):
    if quotation.company_id != company.id:
        raise ValidationError("This quotation does not belong to the active company.")
    if quotation.status != "draft":
        raise ValidationError(f"Cannot send a quotation in '{quotation.status}' status.")
    quotation.status = "sent"
    quotation.save(update_fields=["status"])
    return quotation


def accept_quotation(*, company, quotation):
    if quotation.company_id != company.id:
        raise ValidationError("This quotation does not belong to the active company.")
    if quotation.status not in ("sent", "draft"):
        raise ValidationError(f"Cannot accept a quotation in '{quotation.status}' status.")
    quotation.status = "accepted"
    quotation.save(update_fields=["status"])
    return quotation


def reject_quotation(*, company, quotation):
    if quotation.company_id != company.id:
        raise ValidationError("This quotation does not belong to the active company.")
    quotation.status = "rejected"
    quotation.save(update_fields=["status"])
    return quotation


@transaction.atomic
def create_sales_order(*, company, user, customer, date, lines=None, quotation=None, reference=""):
    """
    Either pass `lines` directly, or pass an accepted `quotation` and
    leave `lines` None to copy its lines verbatim — preserving the
    quoted price exactly (acceptance criteria: "preserve original quoted
    prices/discounts"). No accounting entry, no stock movement.
    """
    if customer.company_id != company.id:
        raise ValidationError("This customer does not belong to the active company.")

    if quotation is not None:
        if quotation.company_id != company.id:
            raise ValidationError("This quotation does not belong to the active company.")
        if quotation.status != "accepted":
            raise ValidationError("Can only convert an accepted quotation into a sales order.")
        if lines is None:
            lines = [
                {"product": ql.product, "quantity": ql.quantity, "unit_price": ql.unit_price}
                for ql in quotation.lines.all()
            ]

    if not lines:
        raise ValidationError("Sales order must have at least one line.")

    from apps.tenants.services import next_counter_value
    order = SalesOrder.objects.create(
        company=company, quotation=quotation, customer=customer, date=date, reference=reference, created_by=user,
        number=f"SO-{next_counter_value(company, 'sales_order'):05d}",
    )
    SalesOrderLine.objects.bulk_create([
        SalesOrderLine(
            sales_order=order, product=l["product"], quantity=l["quantity"], unit_price=l["unit_price"],
            line_total=Decimal(l["quantity"]) * Decimal(l["unit_price"]),
        )
        for l in lines
    ])
    return order


def confirm_sales_order(*, company, sales_order):
    if sales_order.company_id != company.id:
        raise ValidationError("This sales order does not belong to the active company.")
    if sales_order.status != "draft":
        raise ValidationError(f"Cannot confirm a sales order in '{sales_order.status}' status.")
    sales_order.status = "confirmed"
    sales_order.save(update_fields=["status"])
    return sales_order


def cancel_sales_order(*, company, sales_order):
    if sales_order.company_id != company.id:
        raise ValidationError("This sales order does not belong to the active company.")
    if sales_order.status == "delivered":
        raise ValidationError("Cannot cancel a fully delivered sales order.")
    sales_order.status = "cancelled"
    sales_order.save(update_fields=["status"])
    return sales_order


def delivered_quantity(so_line):
    """Live from DeliveryLine rows — never a stored counter."""
    return so_line.delivery_lines.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def invoiced_quantity(so_line):
    """Live from SalesInvoiceLine rows that reference this order line."""
    return so_line.invoiced_lines.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


def _refresh_so_status(sales_order):
    lines = list(sales_order.lines.all())
    total_ordered = sum((l.quantity for l in lines), Decimal("0"))
    total_delivered = sum((delivered_quantity(l) for l in lines), Decimal("0"))
    if total_delivered <= 0:
        new_status = "confirmed"
    elif total_delivered >= total_ordered:
        new_status = "delivered"
    else:
        new_status = "partially_delivered"
    if sales_order.status not in ("cancelled",) and sales_order.status != new_status:
        sales_order.status = new_status
        sales_order.save(update_fields=["status"])


@transaction.atomic
def create_delivery(*, company, user, sales_order, warehouse, date, lines, allow_over_delivery=False):
    """
    lines: [{"so_line": SalesOrderLine, "quantity": Decimal}, ...]

    The actual stock issue point for the order-based flow — posts stock
    movements here and only here; create_invoice_from_order() below never
    touches stock. Rejects delivering more than ordered per line unless
    `allow_over_delivery=True` (a controlled override, gated at the view
    layer behind sales.override_delivery_limits).
    """
    if sales_order.company_id != company.id:
        raise ValidationError("This sales order does not belong to the active company.")
    if sales_order.status not in ("confirmed", "partially_delivered"):
        raise ValidationError(f"Cannot deliver against a sales order in '{sales_order.status}' status.")
    if warehouse.company_id != company.id:
        raise ValidationError("This warehouse does not belong to the active company.")
    if not lines:
        raise ValidationError("Delivery must have at least one line.")

    for l in lines:
        so_line = l["so_line"]
        if so_line.sales_order_id != sales_order.id:
            raise ValidationError("A delivery line's so_line does not belong to this sales order.")
        qty = Decimal(l["quantity"])
        if qty <= 0:
            raise ValidationError("Delivery quantity must be positive.")
        if not allow_over_delivery:
            already = delivered_quantity(so_line)
            if already + qty > so_line.quantity:
                raise ValidationError(
                    f"Cannot deliver {qty} of {so_line.product.name}: only "
                    f"{so_line.quantity - already} remains undelivered on this order line."
                )

    from apps.tenants.services import next_counter_value
    delivery = DeliveryNote.objects.create(
        company=company, sales_order=sales_order, warehouse=warehouse, date=date, delivered_by=user,
        number=f"DN-{next_counter_value(company, 'delivery_note'):05d}",
    )
    DeliveryLine.objects.bulk_create([
        DeliveryLine(
            delivery=delivery, so_line=l["so_line"], quantity=l["quantity"], unit_price=l["so_line"].unit_price,
            line_total=Decimal(l["quantity"]) * l["so_line"].unit_price,
        )
        for l in lines
    ])

    for l in lines:
        if l["so_line"].product.is_stock_tracked:
            record_stock_movement(
                company=company, product=l["so_line"].product, warehouse=warehouse,
                quantity=-Decimal(l["quantity"]), reason="delivery", reference=f"DN#{delivery.id}",
            )

    _refresh_so_status(sales_order)
    return delivery


def create_invoice_from_order(*, company, user, sales_order, lines, warehouse=None, due_date=None,
                               tax_rate=Decimal("0"), discount_amount=Decimal("0"), coupon_code="",
                               date, allow_over_invoicing=False):
    """
    lines: [{"so_line": SalesOrderLine, "quantity": Decimal, "unit_price": Decimal (optional override)}, ...]

    Bills quantities already delivered — rejects invoicing more than
    `delivered − already_invoiced` per line unless `allow_over_invoicing=True`.
    Delegates to create_invoice() so the exact same accounting entry
    (Dr AR, Cr Revenue, tax/discount handling) applies; create_invoice()
    itself skips the stock movement for any line carrying a `so_line`
    (see the change to the loop above), so this never double-decrements
    stock — the delivery already did that.
    """
    if sales_order.company_id != company.id:
        raise ValidationError("This sales order does not belong to the active company.")
    if not lines:
        raise ValidationError("Invoice must have at least one line.")

    for l in lines:
        so_line = l["so_line"]
        if so_line.sales_order_id != sales_order.id:
            raise ValidationError("An invoice line's so_line does not belong to this sales order.")
        qty = Decimal(l["quantity"])
        if qty <= 0:
            raise ValidationError("Invoice quantity must be positive.")
        if not allow_over_invoicing:
            available = delivered_quantity(so_line) - invoiced_quantity(so_line)
            if qty > available:
                raise ValidationError(
                    f"Cannot invoice {qty} of {so_line.product.name}: only {available} delivered-but-uninvoiced "
                    f"on this order line."
                )

    resolved_lines = [
        {
            "product": l["so_line"].product,
            "quantity": Decimal(l["quantity"]),
            "unit_price": Decimal(l.get("unit_price", l["so_line"].unit_price)),
            "so_line": l["so_line"],
        }
        for l in lines
    ]

    invoice = create_invoice(
        company=company, user=user, customer=sales_order.customer, date=date,
        lines=resolved_lines, warehouse=warehouse, due_date=due_date, tax_rate=tax_rate,
        discount_amount=discount_amount, coupon_code=coupon_code,
    )
    invoice.sales_order = sales_order
    invoice.save(update_fields=["sales_order"])
    return invoice
