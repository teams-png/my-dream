from decimal import Decimal
from django.db import models
from apps.tenants.models import TenantScopedModel


class Quotation(TenantScopedModel):
    """
    Phase 33: the customer-facing quote. Never posts an accounting entry
    (acceptance criteria: "quotation and sales order do not post
    accounting entries") — it's a proposal, not a financial event.
    """
    STATUS = [("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted"),
              ("rejected", "Rejected"), ("expired", "Expired")]
    number = models.CharField(max_length=30, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    date = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Null for quotations created before this field existed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class QuotationLine(models.Model):
    """`unit_price` here is the quoted price — copied verbatim onto a
    SalesOrderLine on conversion so the customer's quote is preserved;
    any later price change happens explicitly on the order line, never
    by silently re-deriving it from the product's current price."""
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class SalesOrder(TenantScopedModel):
    """
    Phase 33: the confirmed commitment to sell — still never touches the
    ledger. `status` tracks delivery progress only (draft → confirmed →
    partially_delivered → delivered), the same way Phase 32's
    PurchaseOrder tracks receiving progress only. Invoicing progress is
    tracked separately, live, via invoiced_quantity() in services.py.
    """
    STATUS = [
        ("draft", "Draft"), ("confirmed", "Confirmed"),
        ("partially_delivered", "Partially Delivered"), ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
    number = models.CharField(max_length=30, blank=True)
    quotation = models.ForeignKey(Quotation, null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    reference = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Null for sales orders created before this field existed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class SalesOrderLine(models.Model):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class DeliveryNote(TenantScopedModel):
    """
    One shipment against a SalesOrder — supports partial delivery
    (multiple delivery notes per order). This is where stock actually
    leaves (acceptance criteria: "no double stock decrement" — invoicing
    from an order never moves stock again; only a DeliveryNote does).
    No accounting entry: this system doesn't post COGS on delivery or
    sale (see accounting.services docstrings) — revenue and AR are
    recognized entirely at invoice time, same as the existing direct
    create_invoice() flow.
    """
    number = models.CharField(max_length=30, blank=True)
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="deliveries")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    date = models.DateField()
    delivered_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)


class DeliveryLine(models.Model):
    delivery = models.ForeignKey(DeliveryNote, on_delete=models.CASCADE, related_name="lines")
    so_line = models.ForeignKey(SalesOrderLine, on_delete=models.PROTECT, related_name="delivery_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class SalesInvoice(TenantScopedModel):
    STATUS = [("unpaid", "Unpaid"), ("partial", "Partially Paid"), ("paid", "Paid"), ("void", "Void")]
    sales_order = models.ForeignKey(SalesOrder, null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=30)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default="unpaid")
    currency = models.CharField(max_length=3, default="QAR")
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"))
    transaction_subtotal = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    transaction_tax_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    transaction_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    transaction_amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_breakdown = models.JSONField(default=dict, blank=True)
    coupon_code = models.CharField(max_length=30, blank=True)
    discount_reason = models.CharField(max_length=255, blank=True)
    discount_approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="approved_sales_discounts"
    )
    warehouse = models.ForeignKey("inventory.Warehouse", null=True, blank=True, on_delete=models.SET_NULL)
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("company", "invoice_number")
        indexes = [models.Index(fields=("company", "date", "status")), models.Index(fields=("company", "customer", "due_date"))]


class Coupon(TenantScopedModel):
    DISCOUNT_TYPE = [("percentage", "Percentage"), ("fixed", "Fixed Amount")]
    code = models.CharField(max_length=30)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField()
    expiry_date = models.DateField()
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "code")

    def __str__(self):
        return self.code


class CommercialSettings(TenantScopedModel):
    discount_approval_threshold_percent = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    loyalty_enabled = models.BooleanField(default=True)
    loyalty_currency_per_point = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("0.01"))
    loyalty_spend_per_point = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("10.00"))


class PriceList(TenantScopedModel):
    name = models.CharField(max_length=120)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.CASCADE)
    priority = models.IntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)


class PriceListItem(models.Model):
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ("price_list", "product")


class Promotion(TenantScopedModel):
    DISCOUNT_TYPE = [("percentage", "Percentage"), ("fixed", "Fixed Amount")]
    name = models.CharField(max_length=120)
    product = models.ForeignKey("inventory.Product", null=True, blank=True, on_delete=models.CASCADE)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    priority = models.IntegerField(default=0)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)


class ExchangeRate(TenantScopedModel):
    currency = models.CharField(max_length=3)
    effective_date = models.DateField()
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    source = models.CharField(max_length=120, blank=True)
    is_manual = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "currency", "effective_date")
        ordering = ["-effective_date"]


class TaxScheme(TenantScopedModel):
    name = models.CharField(max_length=120)
    registration_number = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)


class TaxCode(TenantScopedModel):
    CLASSIFICATION = [("taxable", "Taxable"), ("zero_rated", "Zero Rated"), ("exempt", "Exempt")]
    scheme = models.ForeignKey(TaxScheme, on_delete=models.CASCADE, related_name="codes")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    rate = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    inclusive = models.BooleanField(default=False)
    classification = models.CharField(max_length=20, choices=CLASSIFICATION, default="taxable")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "code", "effective_from")


class SalesInvoiceLine(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    tax_code = models.ForeignKey(TaxCode, null=True, blank=True, on_delete=models.PROTECT)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    batch = models.ForeignKey(
        "inventory.ProductBatch", null=True, blank=True, on_delete=models.PROTECT,
        help_text="Phase 31: which batch this line sold from, when the product is batch-tracked "
                   "— lets process_return() restore stock to the same batch where possible.",
    )
    serial = models.ForeignKey(
        "inventory.ProductSerial", null=True, blank=True, on_delete=models.PROTECT,
        help_text="Phase 31: which specific unit this line sold, when the product is serial-tracked.",
    )
    so_line = models.ForeignKey(
        SalesOrderLine, null=True, blank=True, on_delete=models.PROTECT, related_name="invoiced_lines",
        help_text="Phase 33: set when this invoice line bills a delivered SalesOrderLine — lets "
                   "invoiced-vs-delivered quantity be reconciled per order line, and tells "
                   "create_invoice_from_order() this line's stock already left at delivery time.",
    )


class CustomerPayment(TenantScopedModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    invoice = models.ForeignKey(SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    method = models.CharField(max_length=30, default="cash")
    currency = models.CharField(max_length=3, default="QAR")
    transaction_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"))
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)


class SalesReturn(TenantScopedModel):
    REFUND_METHOD = [("cash", "Cash"), ("card", "Card"), ("bank", "Bank"), ("store_credit", "Store Credit")]
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="returns")
    date = models.DateField()
    reason = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    refund_method = models.CharField(max_length=20, choices=REFUND_METHOD, default="cash")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)


class SalesReturnLine(models.Model):
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    batch = models.ForeignKey("inventory.ProductBatch", null=True, blank=True, on_delete=models.PROTECT)
    serial = models.ForeignKey("inventory.ProductSerial", null=True, blank=True, on_delete=models.PROTECT)


class POSShift(TenantScopedModel):
    STATUS = [("open", "Open"), ("closed", "Closed")]
    cashier = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="pos_shifts")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="open")


class POSCashMovement(TenantScopedModel):
    KIND = [("cash_in", "Cash In"), ("cash_out", "Cash Out")]
    shift = models.ForeignKey(POSShift, on_delete=models.PROTECT, related_name="cash_movements")
    kind = models.CharField(max_length=10, choices=KIND)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)


class POSCart(TenantScopedModel):
    STATUS = [("held", "Held"), ("completed", "Completed"), ("cancelled", "Cancelled")]
    shift = models.ForeignKey(POSShift, on_delete=models.PROTECT, related_name="carts")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT)
    reference = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="held")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class POSCartLine(models.Model):
    cart = models.ForeignKey(POSCart, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)


class POSReceipt(TenantScopedModel):
    shift = models.ForeignKey(POSShift, on_delete=models.PROTECT, related_name="receipts")
    invoice = models.OneToOneField(SalesInvoice, on_delete=models.PROTECT, related_name="pos_receipt")
    cart = models.OneToOneField(POSCart, null=True, blank=True, on_delete=models.SET_NULL, related_name="receipt")
    receipt_number = models.CharField(max_length=30)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "receipt_number")


class POSPayment(models.Model):
    receipt = models.ForeignKey(POSReceipt, on_delete=models.PROTECT, related_name="payments")
    customer_payment = models.OneToOneField(CustomerPayment, on_delete=models.PROTECT, related_name="pos_payment")
    method = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=14, decimal_places=2)


class OfflineSaleSync(TenantScopedModel):
    """
    One row per retail POS sale made on a device while it was offline. The
    device's client_id makes syncing idempotent: re-sending the same sale
    (after a dropped connection, a retry or a second tab) never creates a
    second invoice.
    """
    STATUS = [("synced", "Synced"), ("attention", "Needs attention"), ("resolved", "Resolved")]
    CHANNELS = [("offline", "Offline sale"), ("live", "Live till")]
    channel = models.CharField(
        max_length=8, choices=CHANNELS, default="offline",
        help_text="'live' rows only remember a till request id, so a retried checkout never bills twice.",
    )
    client_id = models.UUIDField()
    offline_number = models.CharField(max_length=40)
    device_created_at = models.DateTimeField(null=True, blank=True)
    invoice = models.ForeignKey(SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="offline_syncs")
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12, choices=STATUS, default="synced")
    error = models.CharField(max_length=255, blank=True)
    synced_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "client_id"], name="one_sync_per_offline_sale")]
        ordering = ["-created_at"]

    def __str__(self):
        return self.offline_number


class OnlinePaymentSettings(TenantScopedModel):
    """The business's own payment gateway, so customers can pay invoices online.
    Money goes straight to the business's merchant account; secrets are stored encrypted."""
    PROVIDERS = [("", "Off"), ("skipcash", "SkipCash (Qatar)"), ("razorpay", "Razorpay (India)")]
    provider = models.CharField(max_length=20, choices=PROVIDERS, blank=True)
    test_mode = models.BooleanField(default=True)
    key_id = models.CharField(max_length=255, blank=True)
    client_id = models.CharField(max_length=255, blank=True)
    secret_ciphertext = models.TextField(blank=True)
    webhook_key_ciphertext = models.TextField(blank=True)
    deposit_to = models.CharField(max_length=10, default="bank", help_text="bank or cash — the ledger account payments land in.")
    instructions = models.TextField(blank=True, help_text="Bank transfer / UPI / Fawran details shown to customers.")
    portal_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company",)

    @classmethod
    def load(cls, company):
        obj = cls.objects.filter(company=company).first()
        return obj or cls.objects.create(company=company)

    def _decrypt(self, value):
        from apps.platform_admin.payment_gateways import decrypt_credential
        try:
            return decrypt_credential(value)
        except Exception:
            return ""

    @property
    def secret(self):
        return self._decrypt(self.secret_ciphertext)

    @property
    def webhook_key(self):
        return self._decrypt(self.webhook_key_ciphertext)

    def set_secret(self, field, value):
        from apps.platform_admin.payment_gateways import encrypt_credential
        setattr(self, f"{field}_ciphertext", encrypt_credential(value))

    @property
    def ready(self):
        if self.provider == "skipcash":
            return bool(self.key_id and self.client_id and self.secret_ciphertext)
        if self.provider == "razorpay":
            return bool(self.key_id and self.secret_ciphertext)
        return False


class OnlinePayment(TenantScopedModel):
    """One pay-now attempt by a customer, for an invoice or for their whole balance."""
    STATUS = [("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed")]
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="online_payments")
    invoice = models.ForeignKey(SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="online_payments")
    provider = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3)
    transaction_id = models.CharField(max_length=64, unique=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    status_detail = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    receipts = models.CharField(max_length=255, blank=True, help_text="Invoice numbers the payment was applied to.")

    class Meta:
        ordering = ["-created_at"]
