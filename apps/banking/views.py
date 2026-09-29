from decimal import Decimal

from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.tenants.permissions import HasCompanyPermission
from apps.accounting.serializers import JournalEntrySerializer

from .models import BankAccount, StatementTransaction
from .serializers import (
    BankAccountSerializer, StatementImportBatchSerializer, StatementTransactionSerializer,
    ImportStatementInputSerializer, DepositWithdrawalInputSerializer, TransferInputSerializer,
    MatchTransactionInputSerializer,
)
from .services import (
    record_deposit, record_withdrawal, transfer_between_accounts,
    import_statement_csv, match_transaction, unmatch_transaction,
    suggest_matches, reconciliation_summary,
)


def _as_drf_error(exc):
    return DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))


class BankAccountViewSet(viewsets.ModelViewSet):
    serializer_class = BankAccountSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "banking.view", "retrieve": "banking.view",
        "reconciliation": "banking.view",
        "default": "banking.manage",
    }

    def get_queryset(self):
        return BankAccount.objects.for_company(self.request.company).order_by("name")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

    @action(detail=True, methods=["post"])
    def deposit(self, request, pk=None):
        bank_account = self.get_object()
        serializer = DepositWithdrawalInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            entry = record_deposit(company=request.company, bank_account=bank_account, user=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(JournalEntrySerializer(entry).data, status=201)

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        bank_account = self.get_object()
        serializer = DepositWithdrawalInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            entry = record_withdrawal(company=request.company, bank_account=bank_account, user=request.user, **serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(JournalEntrySerializer(entry).data, status=201)

    @action(detail=True, methods=["post"])
    def transfer(self, request, pk=None):
        from_account = self.get_object()
        serializer = TransferInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            entry = transfer_between_accounts(
                company=request.company, from_account=from_account,
                to_account=data["to_bank_account"], amount=data["amount"], date=data["date"],
                user=request.user, reference=data["reference"], memo=data["memo"],
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(JournalEntrySerializer(entry).data, status=201)

    @action(detail=True, methods=["post"], url_path="import-statement")
    def import_statement(self, request, pk=None):
        bank_account = self.get_object()
        serializer = ImportStatementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data.get("file")
        if uploaded:
            csv_text = uploaded.read().decode("utf-8-sig")
            file_name = uploaded.name
        else:
            csv_text = serializer.validated_data["csv_text"]
            file_name = ""
        try:
            batch = import_statement_csv(
                company=request.company, bank_account=bank_account,
                file_name=file_name, csv_text=csv_text, user=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(StatementImportBatchSerializer(batch).data, status=201)

    @action(detail=True, methods=["get"])
    def reconciliation(self, request, pk=None):
        bank_account = self.get_object()
        as_of = request.query_params.get("as_of")
        try:
            summary = reconciliation_summary(company=request.company, bank_account=bank_account, as_of=as_of)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response({
            "bank_account": BankAccountSerializer(bank_account, context={"request": request}).data,
            "ledger_balance": str(summary["ledger_balance"]),
            "statement_balance": str(summary["statement_balance"]),
            "difference": str(summary["difference"]),
            "unmatched_count": summary["unmatched_count"],
            "matched_count": summary["matched_count"],
        })


class StatementTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """Rows are created only via BankAccountViewSet.import_statement — no
    generic create here, matching the JournalEntryViewSet pattern."""
    serializer_class = StatementTransactionSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "banking.view", "retrieve": "banking.view",
        "suggestions": "banking.view",
        "default": "banking.manage",
    }

    def get_queryset(self):
        qs = StatementTransaction.objects.for_company(self.request.company)
        bank_account_id = self.request.query_params.get("bank_account")
        if bank_account_id:
            qs = qs.filter(bank_account_id=bank_account_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=["get"])
    def suggestions(self, request, pk=None):
        statement_transaction = self.get_object()
        try:
            entries = suggest_matches(company=request.company, statement_transaction=statement_transaction)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(JournalEntrySerializer(entries, many=True).data)

    @action(detail=True, methods=["post"])
    def match(self, request, pk=None):
        statement_transaction = self.get_object()
        serializer = MatchTransactionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            match_transaction(
                company=request.company, statement_transaction=statement_transaction,
                journal_entry=serializer.validated_data["journal_entry"], user=request.user,
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        statement_transaction.refresh_from_db()
        return Response(StatementTransactionSerializer(statement_transaction).data)

    @action(detail=True, methods=["post"])
    def unmatch(self, request, pk=None):
        statement_transaction = self.get_object()
        try:
            unmatch_transaction(company=request.company, statement_transaction=statement_transaction, user=request.user)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        statement_transaction.refresh_from_db()
        return Response(StatementTransactionSerializer(statement_transaction).data)
