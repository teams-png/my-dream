from decimal import Decimal
from django.db import models
from apps.tenants.models import TenantScopedModel


class PurchaseOrder(TenantScopedModel):
    """
    Phase 32: the pure procurement document — never touches the ledger
    (acceptance criteria: "PO does not change ledger"). Approval
    ("confirmed") gates whether goods can be received against it at all.
    Status auto-advances to partially_received/received as GoodsReceiptNotes
    come in (see services.py), tracked live from GRN lines rather than a
    stored counter — same append-only-ledger principle used everywhere
    else in this codebase.
    """
    STATUS = [
        ("draft", "Draft"), ("confirmed", "Confirmed"),
        ("partially_received", "Partially Received"), ("received", "Received"),
        ("cancelled", "Cancelled"),
    ]
    number = models.CharField(max_length=30, blank=True)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    reference = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        help_text="Null for purchase orders created before this field existed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class GoodsReceiptNote(TenantScopedModel):
    """
    One delivery event against a PurchaseOrder — supports partial
    receiving (multiple GRNs per PO). Receiving debits Inventory and
    credits a GRNI (Goods Received Not Invoiced) accrual account rather
    than Accounts Payable directly, since the real liability amount
    isn't confirmed until the supplier's bill arrives (see
    apps.accounting.services.DEFAULT_CHART_OF_ACCOUNTS, account 2050).
    """
    number = models.CharField(max_length=30, blank=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    date = models.DateField()
    received_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)


class GoodsReceiptNoteLine(models.Model):
    grn = models.ForeignKey(GoodsReceiptNote, on_delete=models.CASCADE, related_name="lines")
    po_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)


class Purchase(TenantScopedModel):
    STATUS = [("unpaid", "Unpaid"), ("partial", "Partial"), ("paid", "Paid")]
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL)
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    bill_number = models.CharField(max_length=30, blank=True)
    date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
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
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [models.Index(fields=("company", "date", "status")), models.Index(fields=("company", "supplier", "due_date"))]


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    tax_code = models.ForeignKey("sales.TaxCode", null=True, blank=True, on_delete=models.PROTECT)
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    po_line = models.ForeignKey(
        PurchaseOrderLine, null=True, blank=True, on_delete=models.PROTECT, related_name="billed_lines",
        help_text="Phase 32: set when this bill line was created from a GoodsReceiptNote against a "
                   "PurchaseOrder line — lets billed-vs-received quantity be reconciled per PO line.",
    )


class SupplierPayment(TenantScopedModel):
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    purchase = models.ForeignKey(Purchase, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    method = models.CharField(max_length=30, default="cash")
    currency = models.CharField(max_length=3, default="QAR")
    transaction_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8, default=Decimal("1"))
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)


class PurchaseReturn(TenantScopedModel):
    """
    Mirror of sales.SalesReturn (Phase 27) — same shape, opposite direction:
    goods go back to the supplier instead of coming back from the customer.
    REFUND_METHOD uses "supplier_credit" (reduces what we owe — the common
    B2B case) as the default rather than sales' "cash" default, since most
    purchase returns net off against the next bill rather than a literal
    cash refund from the supplier.
    """
    REFUND_METHOD = [("cash", "Cash"), ("bank", "Bank"), ("supplier_credit", "Supplier Credit")]
    number = models.CharField(max_length=30, blank=True)
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name="returns")
    date = models.DateField()
    reason = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    refund_method = models.CharField(max_length=20, choices=REFUND_METHOD, default="supplier_credit")
    journal_entry = models.OneToOneField("accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL)


class PurchaseReturnLine(models.Model):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
