"""Ask BookPilot: questions about the business answered by Claude from a summary of the business's own figures.

Claude never reaches the database: the view builds a small snapshot (sales by period, top products and customers,
money owed, low stock, expenses) and the model answers only from it. An advanced add-on, not part of any plan: on
for a business only when ANTHROPIC_API_KEY is set on the server (Render → Environment) and a platform admin has
ticked "Ask BookPilot (AI)" in that client's modules. Each business may ask DAILY_LIMIT questions a day."""
import json
import os
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Count, Sum
from django.utils import timezone

MODEL = "claude-opus-5-5"
DAILY_LIMIT = 40
SYSTEM = (
    "You are the assistant inside BookPilot, a business app used by small shops and service businesses. "
    "Answer the owner's question using only the business data in the JSON snapshot you are given. "
    "If the snapshot does not contain what is needed, say so plainly and suggest which BookPilot page or report "
    "would show it. Never invent figures. Keep answers short and practical: a direct answer first, then at most a "
    "few bullet points, with amounts in the business's currency. Reply in the same language as the question."
)


ADDON_CODE = "ai_assistant"


def enabled(company=None):
    """The server has a key and (when a company is given) the platform admin switched the add-on on for it."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    if company is None:
        return True
    from apps.modules.models import CompanyModule
    return CompanyModule.objects.filter(company=company, module__code=ADDON_CODE, is_active=True).exists()


def _money(value):
    return str((value or Decimal("0")).quantize(Decimal("0.01")))


def snapshot(company, today=None):
    """The figures the assistant may use — this business only."""
    from apps.customers.models import Customer
    from apps.expenses.models import Expense
    from apps.sales.models import SalesInvoice, SalesInvoiceLine
    from .overview import _low_stock
    today = today or timezone.localdate()
    month = today.replace(day=1)
    last_month = (month - timedelta(days=1)).replace(day=1)
    invoices = SalesInvoice.objects.for_company(company).exclude(status="void")

    def period(start, end):
        agg = invoices.filter(date__gte=start, date__lte=end).aggregate(total=Sum("total"), bills=Count("id"))
        return {"from": str(start), "to": str(end), "sales": _money(agg["total"]), "bills": agg["bills"]}

    lines = SalesInvoiceLine.objects.filter(invoice__company=company, invoice__date__gte=month).exclude(invoice__status="void")
    top_products = [{"product": r["product__name"], "quantity": str(r["qty"]), "revenue": _money(r["rev"])}
                    for r in lines.values("product__name").annotate(qty=Sum("quantity"), rev=Sum("line_total"))
                    .order_by("-rev")[:10]]
    top_customers = [{"customer": r["customer__name"], "sales": _money(r["t"]), "bills": r["n"]}
                     for r in invoices.filter(date__gte=month).values("customer__name")
                     .annotate(t=Sum("total"), n=Count("id")).order_by("-t")[:10]]
    unpaid = invoices.filter(status__in=["unpaid", "partial"]).select_related("customer")
    overdue = [{"customer": i.customer.name, "invoice": i.invoice_number, "due_date": str(i.due_date),
                "balance": _money(i.total - i.amount_paid)}
               for i in unpaid.filter(due_date__lt=today).order_by("due_date")[:15]]
    owed = sum((i.total - i.amount_paid for i in unpaid), Decimal("0"))
    expenses = [{"category": r["category__name"], "amount": _money(r["t"])}
                for r in Expense.objects.for_company(company).filter(date__gte=month)
                .values("category__name").annotate(t=Sum("amount")).order_by("-t")[:10]]
    return {
        "business": company.name, "business_type": company.business_type.name if company.business_type_id else "",
        "currency": getattr(company, "default_currency", "") or "", "today": str(today),
        "sales": {"today": period(today, today), "last_7_days": period(today - timedelta(days=6), today),
                  "this_month": period(month, today), "last_month": period(last_month, month - timedelta(days=1))},
        "top_products_this_month": top_products,
        "top_customers_this_month": top_customers,
        "money_owed_by_customers": _money(owed),
        "invoices_past_due": overdue,
        "customers_total": Customer.objects.for_company(company).count(),
        "low_stock": [{"product": p.name, "in_stock": str(stock), "reorder_level": p.reorder_level}
                      for stock, p in _low_stock(company)[:15]],
        "expenses_this_month_by_category": expenses,
    }


def used_today(company):
    return cache.get(f"assistant:{company.id}:{timezone.localdate()}", 0)


def _count(company):
    key = f"assistant:{company.id}:{timezone.localdate()}"
    cache.set(key, used_today(company) + 1, 60 * 60 * 26)


def ask(company, question, history=()):
    """Returns (answer_text, error_text). history: [(question, answer), ...] of this browser session, oldest first."""
    import anthropic
    if used_today(company) >= DAILY_LIMIT:
        return "", "limit"
    messages = []
    for q, a in history[-3:]:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    data = json.dumps(snapshot(company), ensure_ascii=False, sort_keys=True)
    messages.append({"role": "user", "content": f"<business_snapshot>\n{data}\n</business_snapshot>\n\n{question}"})
    client = anthropic.Anthropic(timeout=60.0)
    try:
        response = client.beta.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM, messages=messages,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
    except anthropic.RateLimitError:
        return "", "busy"
    except anthropic.APIStatusError as exc:
        return "", "busy" if exc.status_code >= 500 else "error"
    except anthropic.APIConnectionError:
        return "", "busy"
    _count(company)
    if response.stop_reason == "refusal":
        return "", "refused"
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text, ("" if text else "error")
