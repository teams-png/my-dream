from decimal import Decimal
from rest_framework import serializers

from apps.accounting.models import Account
from apps.accounting.serializers import JournalEntrySerializer

from .models import BankAccount, StatementImportBatch, StatementTransaction


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = [
            "id", "name", "account_type", "ledger_account", "bank_name",
            "account_number_last4", "currency", "opening_balance",
            "opening_balance_date", "is_active",
        ]
        read_only_fields = ["id"]

    def validate_ledger_account(self, account):
        request = self.context["request"]
        if account.company_id != request.company.id:
            raise serializers.ValidationError("This account does not belong to the active company.")
        if account.type != "asset":
            raise serializers.ValidationError("A bank/cash account must map to an asset account.")
        return account


class StatementImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatementImportBatch
        fields = [
            "id", "bank_account", "file_name", "row_count",
            "skipped_duplicate_count", "imported_by", "imported_at",
        ]
        read_only_fields = fields


class StatementTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatementTransaction
        fields = [
            "id", "bank_account", "import_batch", "date", "description",
            "reference", "amount", "status", "matched_journal_entry",
            "matched_at", "matched_by",
        ]
        read_only_fields = fields


class ImportStatementInputSerializer(serializers.Serializer):
    file = serializers.FileField(required=False)
    csv_text = serializers.CharField(required=False, allow_blank=False)

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("csv_text"):
            raise serializers.ValidationError("Provide either `file` or `csv_text`.")
        return attrs


class DepositWithdrawalInputSerializer(serializers.Serializer):
    contra_account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    date = serializers.DateField()
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    memo = serializers.CharField(required=False, allow_blank=True, default="")
    statement_transaction = serializers.PrimaryKeyRelatedField(
        queryset=StatementTransaction.objects.all(), required=False, allow_null=True
    )

    def validate_contra_account(self, account):
        request = self.context["request"]
        if account.company_id != request.company.id:
            raise serializers.ValidationError("This account does not belong to the active company.")
        return account


class TransferInputSerializer(serializers.Serializer):
    to_bank_account = serializers.PrimaryKeyRelatedField(queryset=BankAccount.objects.all())
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    date = serializers.DateField()
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    memo = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_to_bank_account(self, account):
        request = self.context["request"]
        if account.company_id != request.company.id:
            raise serializers.ValidationError("This account does not belong to the active company.")
        return account


class MatchTransactionInputSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounting.models import JournalEntry
        self.fields["journal_entry"] = serializers.PrimaryKeyRelatedField(queryset=JournalEntry.objects.all())
