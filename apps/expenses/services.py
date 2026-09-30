from django.utils.dateparse import parse_date
from decimal import Decimal
from django.db import transaction

from apps.accounting.models import Account
from apps.accounting.services import post_journal_entry

from .models import Expense


@transaction.atomic
def record_expense(*, company, user, category, date, amount, description="", payment_method="cash"):
    """Every expense posts Dr General Expenses / Cr Cash-or-Bank — never a bare Expense row
    with no ledger entry (Phase 0 Section 18)."""
    expense = Expense.objects.create(
        company=company, category=category, date=date, amount=amount,
        description=description, payment_method=payment_method,
    )
    cash_code = "1010" if payment_method in ("bank", "card") else "1000"
    accounts = {a.code: a for a in Account.objects.for_company(company).filter(code__in=["5100", cash_code])}
    entry = post_journal_entry(
        company=company, date=date, user=user,
        lines=[(accounts["5100"], Decimal(amount), Decimal("0")), (accounts[cash_code], Decimal("0"), Decimal(amount))],
        reference=f"Expense#{expense.id}", source_type="expense", source_id=expense.id,
    )
    expense.journal_entry = entry
    expense.save(update_fields=["journal_entry"])
    from .budgets import check_budget
    check_budget(company, category, expense.date if hasattr(expense.date, "year") else parse_date(str(expense.date)))
    return expense


DEFAULT_EXPENSE_CATEGORIES = [
    "Rent", "Electricity", "Water", "Internet", "Salary", "Transportation",
    "Marketing", "Maintenance", "Office Supplies", "Other",
]


def seed_default_categories(company):
    """Called once at company signup so an owner never lands on an empty
    Expenses page — these are the categories every business needs regardless
    of vertical (Section 18)."""
    from .models import ExpenseCategory
    for name in DEFAULT_EXPENSE_CATEGORIES:
        ExpenseCategory.objects.get_or_create(company=company, name=name)
