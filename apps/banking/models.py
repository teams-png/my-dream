from django.db import models
from apps.tenants.models import TenantScopedModel


class BankAccount(TenantScopedModel):
    """
    A bank or cash account the company operates, mapped 1:1 onto an asset
    Account in the chart of accounts — `ledger_account` is the single
    source of truth for its balance (accounting.services.account_balance),
    never a balance field stored here. Phase 29 builds real operations
    (deposit/withdrawal/transfer/reconciliation) on top of that mapping.
    """
    TYPE = [("bank", "Bank"), ("cash", "Cash")]

    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=10, choices=TYPE, default="bank")
    ledger_account = models.OneToOneField(
        "accounting.Account", on_delete=models.PROTECT, related_name="bank_account"
    )
    bank_name = models.CharField(max_length=150, blank=True)
    account_number_last4 = models.CharField(max_length=4, blank=True)
    currency = models.CharField(max_length=3, default="QAR")
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    opening_balance_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"


class StatementImportBatch(TenantScopedModel):
    """
    One CSV upload. `fingerprint` is a hash of the raw file content
    (per bank account) so re-uploading the exact same file is rejected
    outright before any row is even parsed (Phase 29: "prevent duplicate
    statement imports").
    """
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="import_batches")
    file_name = models.CharField(max_length=255, blank=True)
    fingerprint = models.CharField(max_length=64)
    row_count = models.PositiveIntegerField(default=0)
    skipped_duplicate_count = models.PositiveIntegerField(default=0)
    imported_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "bank_account", "fingerprint")


class StatementTransaction(TenantScopedModel):
    """
    One row from an imported bank statement. Never posts an accounting
    entry on its own (Phase 29 rule) — it sits here as `unmatched` until
    a human explicitly matches it to a journal entry via
    services.match_transaction(), which is the only thing that flips
    `status` to `matched`.

    `row_fingerprint` dedupes individual rows (date+amount+description+
    reference) *within a bank account*, independent of which batch they
    arrived in — covers overlapping-date-range re-imports, not just an
    identical whole-file re-upload.
    """
    STATUS = [("unmatched", "Unmatched"), ("matched", "Matched")]

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name="statement_transactions")
    import_batch = models.ForeignKey(StatementImportBatch, on_delete=models.CASCADE, related_name="transactions")
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    # Signed: positive = money in (deposit/credit), negative = money out (withdrawal/debit).
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    row_fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=10, choices=STATUS, default="unmatched")
    matched_journal_entry = models.ForeignKey(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    matched_at = models.DateTimeField(null=True, blank=True)
    matched_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        unique_together = ("company", "bank_account", "row_fingerprint")
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date} {self.description} {self.amount}"
