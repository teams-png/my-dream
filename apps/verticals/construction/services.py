"""
record_project_expense mirrors apps.expenses.services.record_expense
exactly (same accounts, same Dr/Cr shape) — the only difference is the
resulting row also carries a `project` FK, which is what makes
project-wise P&L (Phase 0 Section 8, Phase 1 Section 12 "Project-wise
accounting") possible via project_summary() below, without a second ledger
or a parallel chart of accounts.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.accounting.models import Account
from apps.accounting.services import post_journal_entry

from .models import ProjectExpense


@transaction.atomic
def record_project_expense(
    *, company, user, project, category, date, amount, description="",
    payment_method="cash", contractor=None,
):
    expense = ProjectExpense.objects.create(
        company=company, project=project, category=category, contractor=contractor,
        date=date, amount=amount, description=description, payment_method=payment_method,
    )
    cash_code = "1010" if payment_method == "bank" else "1000"
    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["5100", cash_code])}
    entry = post_journal_entry(
        company=company, date=date, user=user,
        lines=[
            (accounts["5100"], Decimal(amount), Decimal("0")),
            (accounts[cash_code], Decimal("0"), Decimal(amount)),
        ],
        reference=f"ProjectExpense#{expense.id} ({project.name})",
        source_type="construction.project_expense", source_id=expense.id,
    )
    expense.journal_entry = entry
    expense.save(update_fields=["journal_entry"])
    return expense


def project_summary(project):
    """
    Cost-tracking view of a project: budget vs actual spend, plus profit
    against the client contract value. Deliberately independent of
    apps.reports — this is a single-project drill-down, not a company-wide
    financial statement.
    """
    expenses = ProjectExpense.objects.filter(project=project)
    total_spent = expenses.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    by_category = list(expenses.values("category").annotate(total=Sum("amount")).order_by("-total"))

    return {
        "project": project.name,
        "budget": project.budget,
        "total_spent": total_spent,
        "budget_remaining": project.budget - total_spent,
        "over_budget": total_spent > project.budget,
        "contract_value": project.contract_value,
        "project_profit": project.contract_value - total_spent,
        "by_category": by_category,
    }
