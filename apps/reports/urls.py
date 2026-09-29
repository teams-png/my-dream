from django.urls import path
from . import views

urlpatterns = [
    path("trial-balance/", views.TrialBalanceView.as_view(), name="report-trial-balance"),
    path("profit-and-loss/", views.ProfitAndLossView.as_view(), name="report-profit-loss"),
    path("balance-sheet/", views.BalanceSheetView.as_view(), name="report-balance-sheet"),
    path("cash-flow/", views.CashFlowView.as_view(), name="report-cash-flow"),
    path("sales/", views.SalesReportView.as_view(), name="report-sales"),
    path("purchases/", views.PurchaseReportView.as_view(), name="report-purchases"),
    path("expenses/", views.ExpenseReportView.as_view(), name="report-expenses"),
    path("tax/", views.TaxReportView.as_view(), name="report-tax"),
    path("stock/", views.StockReportView.as_view(), name="report-stock"),
    path("stock-valuation/", views.StockValuationView.as_view(), name="report-stock-valuation"),
    path("customer-outstanding/", views.CustomerOutstandingView.as_view(), name="report-customer-outstanding"),
    path("supplier-outstanding/", views.SupplierOutstandingView.as_view(), name="report-supplier-outstanding"),
]
