"""Bank & cash accounts: balances, money in/out, transfers, statement import and reconciliation.
Also the company's own audit log and tax / currency setup."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.accounting.models import Account, JournalEntry, JournalLine
from apps.accounting.services import account_balance, post_journal_entry, seed_chart_of_accounts
from apps.audit.models import AuditLog
from apps.banking import services as bank
from apps.banking.models import BankAccount, StatementTransaction
from apps.sales.models import ExchangeRate, TaxCode, TaxScheme

from .views import require_permission

MANAGE = "banking.manage"
VIEW = "banking.view"
ZERO = Decimal("0")


def _err(request, exc):
    messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))


def _amount(value):
    try:
        amount = Decimal(value or "0").quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def _ensure_accounts(company):
    """Every company gets its Cash and Bank ledger accounts as bank/cash accounts."""
    seed_chart_of_accounts(company)
    for code, name, kind in (("1000", _("Cash in hand"), "cash"), ("1010", _("Bank"), "bank")):
        ledger = Account.objects.for_company(company).get(code=code)
        if not BankAccount.objects.filter(ledger_account=ledger).exists():
            BankAccount.objects.create(company=company, name=name, account_type=kind, ledger_account=ledger,
                                       currency=company.default_currency)


def _contra_accounts(company):
    return Account.objects.for_company(company).filter(is_active=True).exclude(bank_account__isnull=False).order_by("code")


@login_required
@require_permission(VIEW)
def bank_home(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    _ensure_accounts(company)
    accounts = list(BankAccount.objects.for_company(company).filter(is_active=True).select_related("ledger_account").order_by("account_type", "name"))
    if request.method == "POST":
        if request.role and not request.role.permissions.filter(permission__code=MANAGE).exists():
            messages.error(request, _("You don't have permission to do that."))
            return redirect("webapp:bank_home")
        action = request.POST.get("action")
        day = parse_date(request.POST.get("date") or "") or timezone.localdate()
        try:
            with transaction.atomic():
                if action == "add":
                    name = (request.POST.get("name") or "").strip()
                    if not name:
                        raise ValidationError(_("Enter a name for the account."))
                    codes = set(Account.objects.for_company(company).values_list("code", flat=True))
                    code = next(str(c) for c in range(1011, 1100) if str(c) not in codes)
                    ledger = Account.objects.create(company=company, code=code, name=name[:150], type="asset")
                    account = BankAccount.objects.create(
                        company=company, name=name[:150], ledger_account=ledger,
                        account_type="cash" if request.POST.get("account_type") == "cash" else "bank",
                        bank_name=(request.POST.get("bank_name") or "")[:150],
                        account_number_last4=(request.POST.get("last4") or "")[-4:], currency=company.default_currency)
                    opening = _amount(request.POST.get("opening"))
                    if opening:
                        equity = Account.objects.for_company(company).get(code="3000")
                        post_journal_entry(company=company, date=day, user=request.user, source_type="manual",
                                           lines=[(ledger, opening, ZERO), (equity, ZERO, opening)],
                                           reference=_("Opening balance"), memo=account.name)
                        account.opening_balance, account.opening_balance_date = opening, day
                        account.save(update_fields=["opening_balance", "opening_balance_date"])
                    messages.success(request, _("Account %(name)s added.") % {"name": account.name})
                elif action == "transfer":
                    source = BankAccount.objects.for_company(company).get(id=request.POST.get("from"))
                    target = BankAccount.objects.for_company(company).get(id=request.POST.get("to"))
                    amount = _amount(request.POST.get("amount"))
                    if not amount:
                        raise ValidationError(_("Enter an amount."))
                    bank.transfer_between_accounts(company=company, from_account=source, to_account=target, amount=amount,
                                                   date=day, user=request.user, reference=(request.POST.get("reference") or "")[:100])
                    messages.success(request, _("%(amount)s moved from %(from)s to %(to)s.") % {
                        "amount": amount, "from": source.name, "to": target.name})
                elif action in ("in", "out"):
                    account = BankAccount.objects.for_company(company).get(id=request.POST.get("account"))
                    contra = _contra_accounts(company).get(id=request.POST.get("contra"))
                    amount = _amount(request.POST.get("amount"))
                    if not amount:
                        raise ValidationError(_("Enter an amount."))
                    record = bank.record_deposit if action == "in" else bank.record_withdrawal
                    record(company=company, bank_account=account, contra_account=contra, amount=amount, date=day,
                           user=request.user, reference=(request.POST.get("reference") or "")[:100],
                           memo=(request.POST.get("memo") or "")[:500])
                    messages.success(request, _("Saved."))
        except (ValidationError, BankAccount.DoesNotExist, Account.DoesNotExist, IntegrityError) as exc:
            _err(request, exc)
        return redirect("webapp:bank_home")
    for account in accounts:
        account.balance = account_balance(account.ledger_account)
        account.unmatched = StatementTransaction.objects.filter(bank_account=account, status="unmatched").count()
    return render(request, "webapp/banking/home.html", {
        "accounts": accounts, "total": sum((a.balance for a in accounts), ZERO), "today": timezone.localdate(),
        "contra": _contra_accounts(company)})


@login_required
@require_permission(VIEW)
def bank_account(request, account_id):
    company = request.company
    account = get_object_or_404(BankAccount.objects.for_company(company).select_related("ledger_account"), id=account_id)
    if request.method == "POST":
        if request.role and not request.role.permissions.filter(permission__code=MANAGE).exists():
            messages.error(request, _("You don't have permission to do that."))
            return redirect("webapp:bank_account", account.id)
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "import":
                    upload = request.FILES.get("statement")
                    if not upload:
                        raise ValidationError(_("Choose the CSV file from your bank."))
                    text = upload.read().decode("utf-8-sig", errors="replace")
                    batch = bank.import_statement_csv(company=company, bank_account=account, file_name=upload.name[:255],
                                                      csv_text=text, user=request.user)
                    messages.success(request, _("%(count)s statement lines imported (%(skipped)s already there).") % {
                        "count": batch.row_count, "skipped": batch.skipped_duplicate_count})
                elif action == "match":
                    row = StatementTransaction.objects.for_company(company).get(id=request.POST.get("row"), bank_account=account)
                    entry = JournalEntry.objects.for_company(company).get(id=request.POST.get("entry"))
                    bank.match_transaction(company=company, statement_transaction=row, journal_entry=entry, user=request.user)
                    messages.success(request, _("Matched."))
                elif action == "unmatch":
                    row = StatementTransaction.objects.for_company(company).get(id=request.POST.get("row"), bank_account=account)
                    bank.unmatch_transaction(company=company, statement_transaction=row, user=request.user)
                elif action == "create":
                    row = StatementTransaction.objects.for_company(company).get(id=request.POST.get("row"), bank_account=account)
                    contra = _contra_accounts(company).get(id=request.POST.get("contra"))
                    record = bank.record_deposit if row.amount > 0 else bank.record_withdrawal
                    record(company=company, bank_account=account, contra_account=contra, amount=abs(row.amount), date=row.date,
                           user=request.user, reference=row.reference[:100], memo=row.description, statement_transaction=row)
                    messages.success(request, _("Entry recorded and matched."))
        except (ValidationError, StatementTransaction.DoesNotExist, JournalEntry.DoesNotExist, Account.DoesNotExist, IntegrityError) as exc:
            _err(request, exc)
        return redirect("webapp:bank_account", account.id)
    unmatched = list(StatementTransaction.objects.for_company(company).filter(bank_account=account, status="unmatched").order_by("date")[:100])
    for row in unmatched:
        row.suggestions = bank.suggest_matches(company=company, statement_transaction=row)[:3]
    lines = (JournalLine.objects.filter(account=account.ledger_account, journal_entry__is_void=False)
             .select_related("journal_entry").order_by("-journal_entry__date", "-journal_entry_id")[:60])
    return render(request, "webapp/banking/account.html", {
        "account": account, "summary": bank.reconciliation_summary(company=company, bank_account=account),
        "unmatched": unmatched, "lines": lines, "contra": _contra_accounts(company),
        "matched": StatementTransaction.objects.for_company(company).filter(bank_account=account, status="matched")
        .select_related("matched_journal_entry").order_by("-date")[:20]})


# ------------------------------------------------------------------ audit log

@login_required
@require_permission("accounting.view_reports")
def audit_log(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    logs = AuditLog.objects.for_company(company).select_related("user").order_by("-timestamp")
    query = (request.GET.get("q") or "").strip()
    if query:
        logs = logs.filter(Q(action__icontains=query) | Q(model_name__icontains=query) | Q(user__email__icontains=query)
                           | Q(user__username__icontains=query) | Q(object_id=query))
    start, end = parse_date(request.GET.get("from") or ""), parse_date(request.GET.get("to") or "")
    if start:
        logs = logs.filter(timestamp__date__gte=start)
    if end:
        logs = logs.filter(timestamp__date__lte=end)
    page = Paginator(logs, 50).get_page(request.GET.get("page"))
    for log in page:
        log.action_label = log.action.replace("_", " ").capitalize()
        log.summary = ", ".join(f"{k}: {v}" for k, v in list((log.changes or {}).items())[:4]) if isinstance(log.changes, dict) else ""
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "webapp/banking/audit.html", {"page": page, "q": query, "start": start, "end": end,
                                                         "page_query": params.urlencode()})


# ------------------------------------------------------------------ tax & currency

@login_required
@require_permission("accounting.post_journal_entry")
def tax_currency(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "scheme":
                    TaxScheme.objects.update_or_create(company=company, defaults={
                        "name": (request.POST.get("name") or "VAT")[:120],
                        "registration_number": (request.POST.get("registration") or "")[:100], "is_active": True})
                    messages.success(request, _("Tax registration saved."))
                elif action == "code":
                    scheme = TaxScheme.objects.for_company(company).first() or TaxScheme.objects.create(company=company, name="VAT")
                    TaxCode.objects.create(
                        company=company, scheme=scheme, code=(request.POST.get("code") or "").strip()[:30] or "VAT",
                        name=(request.POST.get("name") or "").strip()[:120] or "VAT", rate=Decimal(request.POST.get("rate") or "0"),
                        inclusive=bool(request.POST.get("inclusive")),
                        classification=request.POST.get("classification") if request.POST.get("classification") in dict(TaxCode.CLASSIFICATION) else "taxable",
                        effective_from=parse_date(request.POST.get("from") or "") or timezone.localdate())
                    messages.success(request, _("Tax code added."))
                elif action == "toggle_code":
                    code = TaxCode.objects.for_company(company).get(id=request.POST.get("id"))
                    code.is_active = not code.is_active
                    code.save(update_fields=["is_active"])
                elif action == "rate":
                    currency = (request.POST.get("currency") or "").strip().upper()[:3]
                    rate = Decimal(request.POST.get("rate") or "0")
                    if len(currency) != 3 or rate <= 0:
                        raise ValidationError(_("Enter a 3-letter currency code and a rate above zero."))
                    ExchangeRate.objects.update_or_create(
                        company=company, currency=currency,
                        effective_date=parse_date(request.POST.get("date") or "") or timezone.localdate(),
                        defaults={"rate": rate, "source": _("Entered manually"), "is_manual": True})
                    messages.success(request, _("Exchange rate saved."))
        except (ValidationError, InvalidOperation, TaxCode.DoesNotExist, IntegrityError) as exc:
            _err(request, exc)
        return redirect("webapp:tax_currency")
    return render(request, "webapp/banking/tax_currency.html", {
        "scheme": TaxScheme.objects.for_company(company).first(),
        "codes": TaxCode.objects.for_company(company).order_by("-is_active", "code"),
        "rates": ExchangeRate.objects.for_company(company).order_by("currency", "-effective_date")[:60],
        "classifications": TaxCode.CLASSIFICATION, "today": timezone.localdate()})
