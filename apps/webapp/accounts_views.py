"""Accounts for every business: profit & loss, balance sheet, trial balance, cash flow, VAT,
chart of accounts, account ledgers and journal entries. Everything is read from the ledger."""
import calendar
from datetime import date as date_cls, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounting import services as acc
from apps.accounting.models import Account, JournalEntry, JournalLine
from apps.reports import services as reports

from .views import require_permission

VIEW = "accounting.view_reports"
POST = "accounting.post_journal_entry"
ZERO = Decimal("0")
TYPE_ORDER = ["asset", "liability", "equity", "income", "expense"]
TYPE_LABELS = {"asset": gettext_lazy("Assets"), "liability": gettext_lazy("Liabilities"), "equity": gettext_lazy("Equity"),
               "income": gettext_lazy("Income"), "expense": gettext_lazy("Expenses")}
SOURCE_LABELS = {
    "sales_invoice": gettext_lazy("Sales"), "customer_payment": gettext_lazy("Customer payments"),
    "purchase": gettext_lazy("Purchases"), "supplier_payment": gettext_lazy("Supplier payments"),
    "expense": gettext_lazy("Expenses"), "payroll": gettext_lazy("Payroll"), "salary_payment": gettext_lazy("Salaries paid"),
    "salary_advance": gettext_lazy("Salary advances"), "salary_advance_repayment": gettext_lazy("Advance repayments"),
    "sales_return": gettext_lazy("Sales returns"), "purchase_return": gettext_lazy("Purchase returns"),
    "manual": gettext_lazy("Manual entries"), "pos": gettext_lazy("POS sales"),
}


def _source_label(code):
    return SOURCE_LABELS.get(code or "manual", (code or "manual").replace("_", " ").capitalize())


def _period(request):
    """(preset, start, end) from ?period= or ?from=&to=. Defaults to this month."""
    today = timezone.localdate()
    start, end = parse_date(request.GET.get("from") or ""), parse_date(request.GET.get("to") or "")
    if start or end:
        return "custom", start, end or today
    preset = request.GET.get("period") or "month"
    first = today.replace(day=1)
    if preset == "last_month":
        end = first - timedelta(days=1)
        return preset, end.replace(day=1), end
    if preset == "quarter":
        q_start = date_cls(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        return preset, q_start, today
    if preset == "year":
        return preset, date_cls(today.year, 1, 1), today
    if preset == "last_year":
        return preset, date_cls(today.year - 1, 1, 1), date_cls(today.year - 1, 12, 31)
    if preset == "all":
        return preset, None, today
    return "month", first, today


PERIODS = [("month", gettext_lazy("This month")), ("last_month", gettext_lazy("Last month")),
           ("quarter", gettext_lazy("This quarter")), ("year", gettext_lazy("This year")),
           ("last_year", gettext_lazy("Last year")), ("all", gettext_lazy("All time"))]


def _as_of(request):
    return parse_date(request.GET.get("as_of") or "") or timezone.localdate()


def _ctx(request, **extra):
    preset, start, end = _period(request)
    return {"preset": preset, "start": start, "end": end, "periods": PERIODS, **extra}


def _account_balance(company, code, as_of=None):
    account = Account.objects.for_company(company).filter(code=code).first()
    return acc.account_balance(account, as_of) if account else ZERO


# ------------------------------------------------------------------ overview

@login_required
@require_permission(VIEW)
def accounts_home(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    acc.seed_chart_of_accounts(company)
    today = timezone.localdate()
    month = acc.profit_and_loss(company, date_from=today.replace(day=1), date_to=today)
    year = acc.profit_and_loss(company, date_from=date_cls(today.year, 1, 1), date_to=today)
    # last 6 months net profit for the trend bars
    trend, cursor = [], today.replace(day=1)
    for _i in range(6):
        last = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
        pl = acc.profit_and_loss(company, date_from=cursor, date_to=last)
        trend.append({"month": cursor, "income": pl["total_income"], "expense": pl["total_expense"], "net": pl["net_profit"]})
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    trend.reverse()
    peak = max([max(t["income"], t["expense"]) for t in trend] + [Decimal("1")])
    for t in trend:
        t["income_pct"] = int(t["income"] / peak * 100)
        t["expense_pct"] = int(t["expense"] / peak * 100)
    return render(request, "webapp/accounts/home.html", {
        "month": month, "year": year, "trend": trend, "today": today,
        "cash": _account_balance(company, "1000"), "bank": _account_balance(company, "1010"),
        "receivable": _account_balance(company, "1100"), "payable": _account_balance(company, "2000"),
        "tax": _account_balance(company, "2100"),
        "recent": JournalEntry.objects.for_company(company).filter(is_void=False).order_by("-date", "-id")[:8],
    })


# ------------------------------------------------------------------ statements

@login_required
@require_permission(VIEW)
def profit_loss(request):
    company = request.company
    ctx = _ctx(request)
    pl = acc.profit_and_loss(company, date_from=ctx["start"], date_to=ctx["end"])
    cogs = sum((b for a, b in pl["expenses"] if a.code == "5000"), ZERO)
    gross = pl["total_income"] - cogs
    return render(request, "webapp/accounts/profit_loss.html", {
        **ctx, "pl": pl, "cogs": cogs, "gross_profit": gross,
        "operating": [(a, b) for a, b in pl["expenses"] if a.code != "5000"],
        "operating_total": pl["total_expense"] - cogs,
        "margin": (pl["net_profit"] / pl["total_income"] * 100).quantize(Decimal("0.1")) if pl["total_income"] else None,
    })


@login_required
@require_permission(VIEW)
def balance_sheet(request):
    company = request.company
    as_of = _as_of(request)
    bs = acc.balance_sheet(company, as_of=as_of)
    return render(request, "webapp/accounts/balance_sheet.html", {
        "bs": bs, "as_of": as_of, "balanced": bs["total_assets"] == bs["total_liabilities_and_equity"],
        "difference": bs["total_assets"] - bs["total_liabilities_and_equity"]})


@login_required
@require_permission(VIEW)
def trial_balance(request):
    company = request.company
    as_of = _as_of(request)
    rows, total_debit, total_credit = [], ZERO, ZERO
    for account, balance in acc.trial_balance(company, as_of=as_of):
        if not balance:
            continue
        natural_debit = account.type in ("asset", "expense")
        debit = balance if (natural_debit and balance > 0) or (not natural_debit and balance < 0) else ZERO
        credit = balance if (not natural_debit and balance > 0) or (natural_debit and balance < 0) else ZERO
        debit, credit = abs(debit), abs(credit)
        rows.append({"account": account, "debit": debit, "credit": credit})
        total_debit += debit
        total_credit += credit
    return render(request, "webapp/accounts/trial_balance.html", {
        "rows": rows, "as_of": as_of, "total_debit": total_debit, "total_credit": total_credit,
        "balanced": total_debit == total_credit})


@login_required
@require_permission(VIEW)
def cash_flow(request):
    company = request.company
    ctx = _ctx(request)
    cf = reports.cash_flow(company, date_from=ctx["start"], date_to=ctx["end"])
    for row in cf["by_source"]:
        row["label"] = _source_label(row["source_type"])
    return render(request, "webapp/accounts/cash_flow.html", {**ctx, "cf": cf})


@login_required
@require_permission(VIEW)
def vat_report(request):
    company = request.company
    ctx = _ctx(request)
    return render(request, "webapp/accounts/vat.html", {
        **ctx, "tax": reports.tax_report(company, date_from=ctx["start"], date_to=ctx["end"])})


# ------------------------------------------------------------------ chart of accounts & ledger

@login_required
@require_permission(VIEW)
def chart_of_accounts(request):
    company = request.company
    acc.seed_chart_of_accounts(company)
    if request.method == "POST":
        if not request.role or request.role.permissions.filter(permission__code=POST).exists():
            action = request.POST.get("action")
            if action == "add":
                code, name, kind = (request.POST.get("code") or "").strip(), (request.POST.get("name") or "").strip(), request.POST.get("type")
                if not code or not name or kind not in dict(Account.TYPE):
                    messages.error(request, _("Enter a code, a name and a type."))
                else:
                    try:
                        with transaction.atomic():
                            Account.objects.create(company=company, code=code[:20], name=name[:150], type=kind)
                        messages.success(request, _("Account %(code)s added.") % {"code": code})
                    except IntegrityError:
                        messages.error(request, _("An account with this code already exists."))
            elif action in ("deactivate", "activate"):
                account = get_object_or_404(Account.objects.for_company(company), id=request.POST.get("id"))
                if account.is_system_account and action == "deactivate":
                    messages.error(request, _("System accounts can't be switched off."))
                else:
                    account.is_active = action == "activate"
                    account.save(update_fields=["is_active"])
        else:
            messages.error(request, _("You don't have permission to do that."))
        return redirect("webapp:acc_chart")
    groups = []
    accounts = list(Account.objects.for_company(company).order_by("code"))
    for kind in TYPE_ORDER:
        rows = [(a, acc.account_balance(a)) for a in accounts if a.type == kind]
        groups.append({"type": kind, "label": TYPE_LABELS[kind], "rows": rows,
                       "total": sum((b for a, b in rows if a.is_active), ZERO)})
    return render(request, "webapp/accounts/chart.html", {"groups": groups, "types": Account.TYPE})


@login_required
@require_permission(VIEW)
def ledger(request, account_id):
    company = request.company
    account = get_object_or_404(Account.objects.for_company(company), id=account_id)
    ctx = _ctx(request)
    start, end = ctx["start"], ctx["end"]
    natural_debit = account.type in ("asset", "expense")
    opening = acc.account_balance(account, start - timedelta(days=1)) if start else ZERO
    lines = (JournalLine.objects.filter(account=account, journal_entry__is_void=False)
             .select_related("journal_entry").order_by("journal_entry__date", "journal_entry_id", "id"))
    if start:
        lines = lines.filter(journal_entry__date__gte=start)
    if end:
        lines = lines.filter(journal_entry__date__lte=end)
    rows, running = [], opening
    for line in lines[:2000]:
        running += (line.debit - line.credit) if natural_debit else (line.credit - line.debit)
        rows.append({"line": line, "entry": line.journal_entry, "balance": running,
                     "source": _source_label(line.journal_entry.source_type)})
    totals = lines.aggregate(d=Sum("debit"), c=Sum("credit"))
    return render(request, "webapp/accounts/ledger.html", {
        **ctx, "account": account, "rows": rows, "opening": opening, "closing": running,
        "total_debit": totals["d"] or ZERO, "total_credit": totals["c"] or ZERO,
        "accounts": Account.objects.for_company(company).order_by("code")})


# ------------------------------------------------------------------ journal

@login_required
@require_permission(VIEW)
def journal_list(request):
    company = request.company
    ctx = _ctx(request)
    entries = JournalEntry.objects.for_company(company).prefetch_related("lines__account").order_by("-date", "-id")
    if ctx["start"]:
        entries = entries.filter(date__gte=ctx["start"])
    if ctx["end"]:
        entries = entries.filter(date__lte=ctx["end"])
    source = request.GET.get("source") or ""
    if source:
        entries = entries.filter(source_type=source) if source != "manual" else entries.filter(Q(source_type="manual") | Q(source_type=""))
    query = (request.GET.get("q") or "").strip()
    if query:
        entries = entries.filter(Q(reference__icontains=query) | Q(memo__icontains=query))
    page = Paginator(entries, 30).get_page(request.GET.get("page"))
    for entry in page:
        entry.total = sum((line.debit for line in entry.lines.all()), ZERO)
        entry.source_label = _source_label(entry.source_type)
    sources = sorted({s or "manual" for s in JournalEntry.objects.for_company(company).values_list("source_type", flat=True).distinct()})
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "webapp/accounts/journal_list.html", {
        **ctx, "page": page, "source": source, "q": query, "page_query": params.urlencode(),
        "sources": [(s, _source_label(s)) for s in sources]})


@login_required
@require_permission(VIEW)
def journal_detail(request, entry_id):
    company = request.company
    entry = get_object_or_404(JournalEntry.objects.for_company(company).select_related("posted_by"), id=entry_id)
    can_void = entry.source_type in ("", "manual") and not entry.is_void
    if request.method == "POST" and request.POST.get("action") == "void" and can_void:
        if request.role and not request.role.permissions.filter(permission__code=POST).exists():
            messages.error(request, _("You don't have permission to do that."))
        else:
            entry.is_void = True
            entry.save(update_fields=["is_void"])
            from apps.audit.services import log_action
            log_action(company=company, user=request.user, action="void_journal_entry", model_name="JournalEntry",
                       object_id=entry.id, changes={"reference": entry.reference})
            messages.success(request, _("Journal entry cancelled."))
        return redirect("webapp:acc_journal_detail", entry.id)
    lines = list(entry.lines.select_related("account").order_by("-debit", "id"))
    return render(request, "webapp/accounts/journal_detail.html", {
        "entry": entry, "lines": lines, "can_void": can_void, "source": _source_label(entry.source_type),
        "total_debit": sum((l.debit for l in lines), ZERO), "total_credit": sum((l.credit for l in lines), ZERO)})


@login_required
@require_permission(POST)
def journal_add(request):
    company = request.company
    acc.seed_chart_of_accounts(company)
    accounts = Account.objects.for_company(company).filter(is_active=True).order_by("code")
    by_id = {str(a.id): a for a in accounts}
    posted = {"date": request.POST.get("date") or timezone.localdate().isoformat(),
              "reference": request.POST.get("reference", ""), "memo": request.POST.get("memo", ""), "rows": []}
    if request.method == "POST":
        lines, errors = [], []
        for account_id, debit, credit, note in zip(request.POST.getlist("account"), request.POST.getlist("debit"),
                                                   request.POST.getlist("credit"), request.POST.getlist("note")):
            posted["rows"].append({"account": account_id, "debit": debit, "credit": credit, "note": note})
            if not account_id and not debit and not credit:
                continue
            try:
                d = Decimal(debit or "0").quantize(Decimal("0.01"))
                c = Decimal(credit or "0").quantize(Decimal("0.01"))
            except InvalidOperation:
                errors.append(_("Amounts must be numbers."))
                continue
            if account_id not in by_id:
                errors.append(_("Choose an account on every line."))
            elif d < 0 or c < 0 or (d and c) or not (d or c):
                errors.append(_("Each line needs either a debit or a credit."))
            else:
                lines.append((by_id[account_id], d, c))
        day = parse_date(posted["date"])
        if not day:
            errors.append(_("Enter a valid date."))
        if len(lines) < 2:
            errors.append(_("A journal entry needs at least two lines."))
        elif sum(l[1] for l in lines) != sum(l[2] for l in lines):
            errors.append(_("Debits and credits must be equal."))
        if not errors:
            try:
                with transaction.atomic():
                    entry = acc.post_journal_entry(company=company, date=day, lines=lines, user=request.user,
                                                   reference=posted["reference"][:100], memo=posted["memo"],
                                                   source_type="manual")
                messages.success(request, _("Journal entry saved."))
                return redirect("webapp:acc_journal_detail", entry.id)
            except (ValidationError, ValueError) as exc:
                errors.append("; ".join(getattr(exc, "messages", [str(exc)])))
        for error in dict.fromkeys(errors):
            messages.error(request, error)
    while len(posted["rows"]) < 4:
        posted["rows"].append({"account": "", "debit": "", "credit": "", "note": ""})
    return render(request, "webapp/accounts/journal_form.html", {"accounts": accounts, "posted": posted})
