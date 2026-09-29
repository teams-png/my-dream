import csv
from django.http import HttpResponse
from rest_framework import permissions, renderers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.services import trial_balance as _trial_balance
from apps.accounting.services import profit_and_loss as _profit_and_loss
from apps.accounting.services import balance_sheet as _balance_sheet
from apps.accounting.serializers import AccountSerializer
from apps.tenants.permissions import HasCompanyPermission
from . import services
from .models import ReportExport


class _CSVFormatRenderer(renderers.BaseRenderer):
    """
    Exists purely so DRF's content negotiation accepts `?format=csv`
    (Phase 25 bug: without a renderer declaring `format = "csv"`, DRF's
    own negotiation.BaseContentNegotiation.filter_renderers raises Http404
    for that query param — in APIView.dispatch's initial() step, before
    the view method ever runs — regardless of anything _maybe_export does).
    _maybe_export() below builds and returns the actual CSV HttpResponse
    itself, so this renderer's .render() is never called in practice.
    """
    media_type = "text/csv"
    format = "csv"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class BaseReportView(APIView):
    """
    Every report endpoint reads financial/business data scoped to the
    caller's company (Section 22) and must be gated the same way sales,
    purchases, etc. are (Section 7) — Staff has no reason to see P&L,
    trial balance, or outstanding-balance reports. `default` covers the
    only HTTP verb these views expose (GET).
    """
    permission_classes = [permissions.IsAuthenticated, HasCompanyPermission]
    required_permissions = {"default": "accounting.view_reports"}
    renderer_classes = [renderers.JSONRenderer, renderers.BrowsableAPIRenderer, _CSVFormatRenderer]


def _parse_date(request, key):
    val = request.query_params.get(key)
    return val or None  # DRF/DjangoORM will parse the ISO string; invalid values raise 400 naturally


def _maybe_export(request, report_code, data, flat_rows=None):
    """
    ?format=csv on any report endpoint downloads the report instead of
    returning JSON, and logs the export (Phase 0 Section 22 / audit trail).
    `flat_rows` must be a list[dict] with uniform keys — pass the most
    tabular part of `data` for reports that aren't naturally one flat table.
    """
    fmt = request.query_params.get("format")
    if fmt != "csv":
        return None

    rows = flat_rows if flat_rows is not None else [data]
    ReportExport.objects.create(
        company=request.company, user=request.user, report_code=report_code, format="csv",
        date_from=request.query_params.get("date_from") or None,
        date_to=request.query_params.get("date_to") or None,
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{report_code}.csv"'
    if rows:
        writer = csv.DictWriter(response, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return response


class ProfitAndLossView(BaseReportView):

    def get(self, request):
        data = _profit_and_loss(
            request.company, _parse_date(request, "date_from"), _parse_date(request, "date_to")
        )
        exported = _maybe_export(request, "profit_and_loss", data, data["income"] + data["expenses"])
        return exported or Response(data)


class BalanceSheetView(BaseReportView):

    def get(self, request):
        data = _balance_sheet(request.company, _parse_date(request, "as_of"))
        exported = _maybe_export(
            request, "balance_sheet", data, data["assets"] + data["liabilities"] + data["equity"]
        )
        return exported or Response(data)


class TrialBalanceView(BaseReportView):

    def get(self, request):
        rows = _trial_balance(request.company, _parse_date(request, "as_of"))
        flat = [{"code": a.code, "name": a.name, "type": a.type, "balance": str(bal)} for a, bal in rows]
        exported = _maybe_export(request, "trial_balance", flat, flat)
        return exported or Response({
            "rows": [{"account": AccountSerializer(a).data, "balance": str(bal)} for a, bal in rows]
        })


class CashFlowView(BaseReportView):

    def get(self, request):
        data = services.cash_flow(
            request.company, _parse_date(request, "date_from"), _parse_date(request, "date_to")
        )
        exported = _maybe_export(request, "cash_flow", data, [data])
        return exported or Response(data)


class SalesReportView(BaseReportView):

    def get(self, request):
        data = services.sales_report(
            request.company,
            _parse_date(request, "date_from"), _parse_date(request, "date_to"),
            request.query_params.get("customer_id"),
        )
        exported = _maybe_export(request, "sales", data, data["by_status"])
        return exported or Response(data)


class PurchaseReportView(BaseReportView):

    def get(self, request):
        data = services.purchase_report(
            request.company,
            _parse_date(request, "date_from"), _parse_date(request, "date_to"),
            request.query_params.get("supplier_id"),
        )
        exported = _maybe_export(request, "purchases", data, [data])
        return exported or Response(data)


class ExpenseReportView(BaseReportView):

    def get(self, request):
        data = services.expense_report(
            request.company,
            _parse_date(request, "date_from"), _parse_date(request, "date_to"),
            request.query_params.get("category_id"),
        )
        exported = _maybe_export(request, "expenses", data, data["by_category"])
        return exported or Response(data)


class TaxReportView(BaseReportView):

    def get(self, request):
        data = services.tax_report(
            request.company, _parse_date(request, "date_from"), _parse_date(request, "date_to")
        )
        exported = _maybe_export(request, "tax", data, [data])
        return exported or Response(data)


class StockReportView(BaseReportView):

    def get(self, request):
        data = services.stock_report(request.company, request.query_params.get("warehouse_id"))
        exported = _maybe_export(request, "stock", data, data["products"])
        return exported or Response(data)


class StockValuationView(BaseReportView):

    def get(self, request):
        data = services.stock_valuation(request.company)
        exported = _maybe_export(request, "stock_valuation", data, data["products"])
        return exported or Response(data)


class CustomerOutstandingView(BaseReportView):

    def get(self, request):
        data = services.customer_outstanding(request.company)
        exported = _maybe_export(request, "customer_outstanding", data, data["customers"])
        return exported or Response(data)


class SupplierOutstandingView(BaseReportView):

    def get(self, request):
        data = services.supplier_outstanding(request.company)
        exported = _maybe_export(request, "supplier_outstanding", data, data["suppliers"])
        return exported or Response(data)
