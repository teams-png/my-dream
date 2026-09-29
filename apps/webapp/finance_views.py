"""Finance tools: post-dated cheques, recurring invoices and fixed assets."""
from datetime import timedelta
from functools import wraps
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.customers.models import Customer
from apps.finance import services
from apps.finance.models import FixedAsset, PostDatedCheque, RecurringInvoice, RecurringInvoiceLine
from apps.inventory.models import Product, Warehouse
from apps.purchases.models import Purchase
from apps.sales.models import SalesInvoice
from apps.suppliers.models import Supplier

from .views import require_permission

PERMISSION = "accounting.post_journal_entry"
DATE = forms.DateInput(attrs={"type": "date"})


def finance_view(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if getattr(request, "company", None) is None:
            return redirect("webapp:dashboard")
        return view(request, *args, **kwargs)
    return login_required(require_permission(PERMISSION)(wrapped))


class ChequeForm(forms.Form):
    direction = forms.ChoiceField(choices=PostDatedCheque.DIRECTION, widget=forms.RadioSelect, initial="received")
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    invoice = forms.ModelChoiceField(queryset=SalesInvoice.objects.none(), required=False, label=_("Against invoice (optional)"))
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none(), required=False)
    purchase = forms.ModelChoiceField(queryset=Purchase.objects.none(), required=False, label=_("Against bill (optional)"))
    cheque_number = forms.CharField(max_length=40)
    bank_name = forms.CharField(max_length=120, required=False)
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    cheque_date = forms.DateField(widget=DATE, label=_("Cheque date"))
    received_on = forms.DateField(widget=DATE, required=False, label=_("Received / issued on"))
    notes = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
        self.fields["supplier"].queryset = Supplier.objects.for_company(company)
        self.fields["invoice"].queryset = SalesInvoice.objects.for_company(company).exclude(status__in=["paid", "void"]).select_related("customer")
        self.fields["purchase"].queryset = Purchase.objects.for_company(company).exclude(status="paid").select_related("supplier")


class RecurringForm(forms.ModelForm):
    class Meta:
        model = RecurringInvoice
        fields = ["name", "customer", "warehouse", "frequency", "next_run_date", "end_date", "tax_percent", "email_customer"]
        widgets = {"next_run_date": DATE, "end_date": DATE}
        labels = {"next_run_date": _("First invoice date"), "end_date": _("Stop after (optional)"), "warehouse": _("Branch")}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)


class AssetForm(forms.ModelForm):
    class Meta:
        model = FixedAsset
        fields = ["name", "category", "asset_code", "purchase_date", "cost", "salvage_value", "useful_life_months", "paid_from", "notes"]
        widgets = {"purchase_date": DATE}
        labels = {"useful_life_months": _("Useful life (months)"), "salvage_value": _("Value at end of life")}


@finance_view
def finance_home(request):
    company = request.company
    today = timezone.localdate()
    cheques = PostDatedCheque.objects.for_company(company)
    open_cheques = cheques.filter(status__in=["pending", "deposited"])
    assets = FixedAsset.objects.for_company(company).filter(status="active").prefetch_related("depreciation_entries")
    return render(request, "webapp/finance/home.html", {
        "due_week": services.cheques_due(company, 7).select_related("customer", "supplier")[:8],
        "to_receive": open_cheques.filter(direction="received").aggregate(t=Sum("amount"))["t"] or 0,
        "to_pay": open_cheques.filter(direction="issued").aggregate(t=Sum("amount"))["t"] or 0,
        "recurring": RecurringInvoice.objects.for_company(company).filter(is_active=True).select_related("customer")[:6],
        "recurring_due": RecurringInvoice.objects.for_company(company).filter(is_active=True, next_run_date__lte=today).count(),
        "asset_count": assets.count(),
        "asset_book_value": sum((a.book_value for a in assets), Decimal("0")),
        "today": today,
    })


@finance_view
def cheque_list(request):
    company = request.company
    status = request.GET.get("status", "open")
    qs = PostDatedCheque.objects.for_company(company).select_related("customer", "supplier", "invoice", "purchase")
    if status == "open":
        qs = qs.filter(status__in=["pending", "deposited"])
    elif status in dict(PostDatedCheque.STATUS):
        qs = qs.filter(status=status)
    form = ChequeForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            services.register_cheque(
                company=company, user=request.user, direction=d["direction"], amount=d["amount"],
                cheque_number=d["cheque_number"], cheque_date=d["cheque_date"], received_on=d.get("received_on"),
                customer=d["customer"] if d["direction"] == "received" else None,
                supplier=d["supplier"] if d["direction"] == "issued" else None,
                invoice=d["invoice"] if d["direction"] == "received" else None,
                purchase=d["purchase"] if d["direction"] == "issued" else None,
                bank_name=d["bank_name"], notes=d["notes"],
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, _("Cheque saved."))
            return redirect("webapp:cheque_list")
    return render(request, "webapp/finance/cheques.html", {
        "cheques": qs, "form": form, "status": status, "today": timezone.localdate(),
        "soon": timezone.localdate() + timedelta(days=3), "statuses": PostDatedCheque.STATUS,
    })


@finance_view
def cheque_status(request, cheque_id):
    cheque = get_object_or_404(PostDatedCheque.objects.for_company(request.company), id=cheque_id)
    if request.method == "POST":
        try:
            services.update_cheque_status(company=request.company, user=request.user, cheque=cheque,
                                          status=request.POST.get("status"), reason=request.POST.get("reason", ""))
            messages.success(request, _("Cheque updated."))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    return redirect(request.POST.get("next") or "webapp:cheque_list")


@finance_view
def recurring_list(request):
    company = request.company
    default_wh = Warehouse.objects.for_company(company).filter(is_active=True).order_by("-is_default", "id").first()
    form = RecurringForm(request.POST or None, company=company,
                         initial={"next_run_date": timezone.localdate(), "warehouse": default_wh})
    products = Product.objects.for_company(company).filter(is_active=True).order_by("name")
    if request.method == "POST":
        product_ids = request.POST.getlist("line_product")
        quantities = request.POST.getlist("line_qty")
        prices = request.POST.getlist("line_price")
        lines = []
        for pid, qty, price in zip(product_ids, quantities, prices):
            if not pid:
                continue
            try:
                lines.append((products.get(id=pid), Decimal(qty or "1"), Decimal(price)))
            except Exception:
                messages.error(request, _("Check the quantity and price on every line."))
                lines = None
                break
        if lines == []:
            messages.error(request, _("Add at least one line."))
        elif lines and form.is_valid():
            rec = form.save(commit=False)
            rec.company, rec.created_by = company, request.user
            rec.save()
            RecurringInvoiceLine.objects.bulk_create([RecurringInvoiceLine(recurring=rec, product=p, quantity=q, unit_price=u) for p, q, u in lines])
            messages.success(request, _("Recurring invoice created."))
            return redirect("webapp:recurring_list")
        elif lines and not form.is_valid():
            messages.error(request, _("Please fix the highlighted fields."))
    return render(request, "webapp/finance/recurring.html", {
        "form": form, "products": products,
        "items": RecurringInvoice.objects.for_company(company).select_related("customer", "last_invoice").prefetch_related("lines"),
    })


@finance_view
def recurring_action(request, recurring_id):
    rec = get_object_or_404(RecurringInvoice.objects.for_company(request.company), id=recurring_id)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "run":
            try:
                created = services.run_recurring_invoice(rec, request_base_url=request.build_absolute_uri("/"))
                messages.success(request, _("%(n)s invoice(s) created.") % {"n": len(created)} if created else _("Nothing due yet."))
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
        elif action in {"pause", "resume"}:
            rec.is_active = action == "resume"
            rec.save(update_fields=["is_active"])
    return redirect("webapp:recurring_list")


@finance_view
def asset_list(request):
    company = request.company
    form = AssetForm(request.POST or None, initial={"purchase_date": timezone.localdate(), "useful_life_months": 60})
    if request.method == "POST" and request.POST.get("action") == "depreciate":
        posted = services.run_depreciation(company=company, user=request.user)
        messages.success(request, _("%(n)s depreciation entries posted.") % {"n": len(posted)} if posted else _("Depreciation is already up to date."))
        return redirect("webapp:asset_list")
    if request.method == "POST" and form.is_valid():
        try:
            services.register_asset(company=company, user=request.user, **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, _("Asset added and recorded in the books."))
            return redirect("webapp:asset_list")
    elif request.method == "POST":
        messages.error(request, _("Please fix the highlighted fields."))
    assets = FixedAsset.objects.for_company(company).prefetch_related("depreciation_entries")
    return render(request, "webapp/finance/assets.html", {
        "form": form, "assets": assets,
        "total_cost": sum((a.cost for a in assets if a.status == "active"), Decimal("0")),
        "total_book": sum((a.book_value for a in assets if a.status == "active"), Decimal("0")),
    })


@finance_view
def asset_dispose(request, asset_id):
    asset = get_object_or_404(FixedAsset.objects.for_company(request.company), id=asset_id)
    if request.method == "POST":
        try:
            services.dispose_asset(company=request.company, user=request.user, asset=asset,
                                   on=timezone.localdate(), amount=request.POST.get("amount") or 0,
                                   received_in=request.POST.get("received_in", "bank"))
            messages.success(request, _("Asset disposed and the gain or loss recorded."))
        except (ValidationError, ArithmeticError) as exc:
            messages.error(request, " ".join(getattr(exc, "messages", [str(exc)])))
    return redirect("webapp:asset_list")
