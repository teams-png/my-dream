from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.tenants.permissions import HasCompanyPermission

from .models import Account, JournalEntry, FiscalYear
from .serializers import AccountSerializer, JournalEntrySerializer, FiscalYearSerializer
from .services import trial_balance, close_fiscal_year, reopen_fiscal_year


class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Chart of accounts is seeded per company and editable, but never through a
    generic create — new accounts go through a dedicated service call so
    is_system_account can't be forged from the API (Phase 0 Section 9).
    """
    serializer_class = AccountSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "accounting.view_reports"}

    def get_queryset(self):
        return Account.objects.for_company(self.request.company).order_by("code")


class JournalEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Journal entries are never created directly via the API — only through
    accounting.services.post_journal_entry(), called by other apps' services."""
    serializer_class = JournalEntrySerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "accounting.view_reports"}

    def get_queryset(self):
        return (
            JournalEntry.objects.for_company(self.request.company)
            .prefetch_related("lines").order_by("-date", "-id")
        )


class TrialBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "accounting.view_reports"}

    def get(self, request):
        rows = trial_balance(request.company)
        return Response([
            {"account": AccountSerializer(a).data, "balance": str(balance)}
            for a, balance in rows
        ])


class FiscalYearViewSet(viewsets.ModelViewSet):
    """
    Fiscal years are created/viewed by anyone with accounting.manage_fiscal_years
    (Owner + Accountant by default). Closing also only needs that permission.
    Reopening a closed year is deliberately gated behind the stricter
    accounting.override_period_lock (Owner only by default) — see Phase 28
    acceptance criteria: reopening must be an explicit, high-privilege action.
    """
    serializer_class = FiscalYearSerializer
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {
        "list": "accounting.view_reports",
        "retrieve": "accounting.view_reports",
        "create": "accounting.manage_fiscal_years",
        "update": "accounting.manage_fiscal_years",
        "partial_update": "accounting.manage_fiscal_years",
        "close": "accounting.manage_fiscal_years",
        "reopen": "accounting.override_period_lock",
        "default": "accounting.view_reports",
    }

    def get_queryset(self):
        return FiscalYear.objects.for_company(self.request.company).order_by("-start_date")

    def perform_create(self, serializer):
        serializer.save(company=self.request.company)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        fiscal_year = self.get_object()
        try:
            entry = close_fiscal_year(company=request.company, fiscal_year=fiscal_year, user=request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))
        fiscal_year.refresh_from_db()
        return Response({
            "fiscal_year": FiscalYearSerializer(fiscal_year).data,
            "closing_journal_entry": JournalEntrySerializer(entry).data if entry else None,
        })

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        fiscal_year = self.get_object()
        try:
            reopen_fiscal_year(company=request.company, fiscal_year=fiscal_year, user=request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.messages if hasattr(exc, "messages") else str(exc))
        fiscal_year.refresh_from_db()
        return Response(FiscalYearSerializer(fiscal_year).data)
