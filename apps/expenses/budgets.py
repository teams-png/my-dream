"""Monthly budgets per expense category: spent vs budget and an alert when the limit is near or crossed."""
import calendar
from datetime import date as date_cls
from decimal import Decimal

from django.db.models import Sum

from .models import Expense, ExpenseBudget, ExpenseCategory

ZERO = Decimal("0")


def month_range(day):
    return day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1])


def month_rows(company, day):
    """[{category, budget, spent, percent, state}] for every category that has a budget or spending this month."""
    start, end = month_range(day)
    spent = dict(Expense.objects.for_company(company).filter(date__range=(start, end)).values_list("category_id")
                 .annotate(t=Sum("amount")))
    budgets = {b.category_id: b for b in ExpenseBudget.objects.for_company(company)}
    rows = []
    for category in ExpenseCategory.objects.for_company(company).order_by("name"):
        budget = budgets.get(category.id)
        used = spent.get(category.id) or ZERO
        if not budget and not used:
            rows.append({"category": category, "budget": None, "spent": ZERO, "percent": None, "state": "none"})
            continue
        percent = int(used / budget.monthly_amount * 100) if budget and budget.monthly_amount else None
        state = "none" if percent is None else "over" if percent >= 100 else "near" if percent >= budget.alert_percent else "ok"
        rows.append({"category": category, "budget": budget, "spent": used, "percent": percent, "state": state,
                     "left": (budget.monthly_amount - used) if budget else None})
    return rows


def check_budget(company, category, day):
    """Called after an expense is saved. Notifies once per month at the warning level and once when exceeded."""
    budget = ExpenseBudget.objects.for_company(company).filter(category=category).first()
    if not budget or budget.monthly_amount <= 0:
        return None
    from apps.notifications.rules import once
    from apps.notifications.services import notify
    start, end = month_range(day)
    used = Expense.objects.for_company(company).filter(category=category, date__range=(start, end)).aggregate(t=Sum("amount"))["t"] or ZERO
    percent = used / budget.monthly_amount * 100
    level = 100 if percent >= 100 else budget.alert_percent if percent >= budget.alert_percent else None
    if level is None or not once(company, f"budget:{category.id}:{start:%Y-%m}:{level}"):
        return None
    if level == 100:
        title = f"Budget exceeded: {category.name} ({int(percent)}%)"
    else:
        title = f"Budget {int(percent)}% used: {category.name}"
    return notify(company=company, notif_type="general", title=title,
                  message=f"Spent {used:.2f} of {budget.monthly_amount:.2f} in {start:%B %Y}.")
