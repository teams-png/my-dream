"""Restaurant mess: monthly meal plans, members, daily meal tick, mess cut, monthly bills and dues."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from apps.customers.models import Customer
from apps.industry import mess as svc
from apps.industry.models import MessCharge, MessLeave, MessMember, MessPlan

from .industry_access import require_industry
from .views import require_permission
from apps.common.ids import pick_id

DATE = forms.DateInput(attrs={"type": "date"})


def mess_view(view):
    return require_industry("mess")(require_permission("restaurant.manage")(view))


def _month(request):
    key = (request.GET.get("month") or request.POST.get("month") or "").strip()
    try:
        svc.month_bounds(key)
        return key
    except (ValueError, TypeError):
        return svc.month_key(timezone.localdate())


def _shift(key, months):
    first, _end = svc.month_bounds(key)
    year, month = first.year, first.month + months
    year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
    return f"{year:04d}-{month:02d}"


# ------------------------------------------------------------------ forms

class PlanForm(forms.ModelForm):
    class Meta:
        model = MessPlan
        fields = ["name", "breakfast", "lunch", "dinner", "monthly_fee", "leave_refund_per_day", "min_leave_days",
                  "description", "is_active"]
        labels = {"name": _l("Plan name"), "breakfast": _l("Breakfast"), "lunch": _l("Lunch"), "dinner": _l("Dinner"),
                  "monthly_fee": _l("Monthly fee"), "leave_refund_per_day": _l("Mess-cut refund per day"),
                  "min_leave_days": _l("Minimum mess-cut days"), "description": _l("Description"),
                  "is_active": _l("Open for new members")}
        help_texts = {"leave_refund_per_day": _l("Taken off the next bill for each day away. 0 = no refund."),
                      "min_leave_days": _l("Shorter leaves are not refunded.")}
        widgets = {"name": forms.TextInput(attrs={"placeholder": _l("e.g. Full mess – 3 meals")}),
                   "description": forms.TextInput(attrs={"placeholder": _l("e.g. Kerala meals, chicken twice a week")})}

    def clean(self):
        data = super().clean()
        if not any(data.get(m) for m in svc.MEALS):
            raise ValidationError(_("Tick at least one meal."))
        return data


class JoinForm(forms.Form):
    plan = forms.ModelChoiceField(queryset=MessPlan.objects.none(), label=_l("Plan"))
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False, label=_l("Existing customer"))
    new_customer_name = forms.CharField(max_length=255, required=False, label=_l("…or new member name"))
    new_customer_phone = forms.CharField(max_length=20, required=False, label=_l("Phone / WhatsApp"))
    start_date = forms.DateField(widget=DATE, label=_l("Starts on"))
    monthly_fee = forms.DecimalField(min_value=0, decimal_places=2, required=False, label=_l("Special monthly fee"),
                                     help_text=_l("Leave empty to use the plan's fee."))
    notes = forms.CharField(max_length=255, required=False, label=_l("Notes"),
                            widget=forms.TextInput(attrs={"placeholder": _l("e.g. Room 12, Al Noor Trading staff, no beef")}))
    bill_now = forms.BooleanField(required=False, initial=True, label=_l("Bill this month now"))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = MessPlan.objects.for_company(company).filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True).order_by("name")

    def clean(self):
        data = super().clean()
        if not data.get("customer") and not (data.get("new_customer_name") or "").strip():
            raise ValidationError(_("Choose a customer or type the new member's name."))
        return data


class MemberForm(forms.ModelForm):
    class Meta:
        model = MessMember
        fields = ["plan", "monthly_fee", "notes"]
        labels = {"plan": _l("Plan"), "monthly_fee": _l("Special monthly fee"), "notes": _l("Notes")}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = MessPlan.objects.for_company(company)


class LeaveForm(forms.Form):
    from_date = forms.DateField(widget=DATE, label=_l("From"))
    to_date = forms.DateField(widget=DATE, label=_l("Until"))
    reason = forms.CharField(max_length=150, required=False, label=_l("Reason"),
                             widget=forms.TextInput(attrs={"placeholder": _l("e.g. Going home on vacation")}))


# ------------------------------------------------------------------ pages

@mess_view
def mess_home(request):
    company = request.company
    if request.method == "POST":
        member = get_object_or_404(MessMember.objects.for_company(company), id=pick_id(request.POST.get("member")))
        meal = request.POST.get("meal")
        try:
            if request.POST.get("action") == "undo":
                svc.undo(member=member, meal=meal)
            else:
                svc.serve(company=company, user=request.user, member=member, meal=meal)
                messages.success(request, _("%(meal)s served to %(name)s.") % {"meal": _(meal.capitalize()), "name": member.customer.name})
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        q = request.POST.get("q", "")
        return redirect(f"{request.path}?q={q}" if q else request.path)
    q = (request.GET.get("q") or "").strip()
    today = timezone.localdate()
    members = svc.running_on(company, today).select_related("customer", "plan")
    if q:
        members = members.filter(Q(customer__name__icontains=q) | Q(customer__phone__icontains=q) | Q(number__icontains=q))
    members = list(members.order_by("number")[:200])
    served = svc.served_today(company, [m.pk for m in members])
    away = set(MessLeave.objects.for_company(company).filter(from_date__lte=today, to_date__gte=today)
               .values_list("member_id", flat=True))
    rows = [{"m": m, "served": served.get(m.pk, set()), "away": m.pk in away, "meals": m.plan.meals()} for m in members]
    key = svc.month_key(today)
    dues = svc.dues(company)
    return render(request, "webapp/mess/home.html", {
        "rows": rows, "q": q, "count": svc.today(company), "plans": MessPlan.objects.for_company(company).exists(),
        "not_billed": len(svc.due_for_month(company, key)), "month": key,
        "dues_total": sum((r["due"] for r in dues), 0), "dues_count": len(dues),
        "paused": MessMember.objects.for_company(company).filter(status="paused").count(),
    })


@mess_view
def mess_plans(request):
    company = request.company
    plans = MessPlan.objects.for_company(company).annotate(
        active=Count("members", filter=Q(members__status="active"))).order_by("-is_active", "name")
    return render(request, "webapp/mess/plans.html", {"plans": plans})


@mess_view
def mess_plan_form(request, plan_id=None):
    company = request.company
    plan = get_object_or_404(MessPlan.objects.for_company(company), id=plan_id) if plan_id else None
    form = PlanForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.company = company
        obj.save()
        svc.plan_product(obj)
        messages.success(request, _("Plan saved."))
        return redirect("webapp:mess_plans")
    return render(request, "webapp/mess/form.html", {"form": form, "title": _("Edit plan") if plan else _("New mess plan"),
                                                       "back": "webapp:mess_plans"})


@mess_view
def mess_join(request):
    company = request.company
    if not MessPlan.objects.for_company(company).filter(is_active=True).exists():
        messages.info(request, _("Create a mess plan first."))
        return redirect("webapp:mess_plan_add")
    form = JoinForm(request.POST or None, company=company, initial={"start_date": timezone.localdate(), "bill_now": True})
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        customer = data.get("customer")
        try:
            if customer is None:
                customer = Customer.objects.create(company=company, name=data["new_customer_name"].strip()[:255],
                                                   phone=(data.get("new_customer_phone") or "").strip()[:20])
            member = svc.join(company=company, user=request.user, plan=data["plan"], customer=customer,
                              start_date=data["start_date"], monthly_fee=data.get("monthly_fee"), notes=data.get("notes") or "",
                              bill_now=data.get("bill_now"))
            messages.success(request, _("%(name)s joined the mess as %(number)s.") % {"name": customer.name, "number": member.number})
            return redirect("webapp:mess_member", member.id)
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
    return render(request, "webapp/mess/form.html", {"form": form, "title": _("New mess member"), "back": "webapp:mess_home"})


@mess_view
def mess_member(request, member_id):
    company = request.company
    member = get_object_or_404(MessMember.objects.for_company(company).select_related("customer", "plan"), id=member_id)
    form = MemberForm(request.POST if request.POST.get("action") == "edit" else None, instance=member, company=company)
    leave_form = LeaveForm(request.POST if request.POST.get("action") == "leave" else None,
                           initial={"from_date": timezone.localdate(), "to_date": timezone.localdate() + timedelta(days=6)})
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "edit" and form.is_valid():
                form.save()
                messages.success(request, _("Saved."))
                return redirect(request.path)
            if action == "leave" and leave_form.is_valid():
                d = leave_form.cleaned_data
                svc.add_leave(company=company, member=member, from_date=d["from_date"], to_date=d["to_date"], reason=d["reason"])
                messages.success(request, _("Mess cut saved."))
                return redirect(request.path)
            if action == "delete_leave":
                MessLeave.objects.filter(member=member, id=pick_id(request.POST.get("leave"))).delete()
                return redirect(request.path)
            if action in ("active", "paused", "ended"):
                svc.set_status(member, action)
                messages.success(request, _("Status changed."))
                return redirect(request.path)
            if action == "bill":
                invoices = svc.bill(company=company, user=request.user, members=[member], key=_month(request))
                messages.success(request, _("Bill created.") if invoices else _("This month is already billed."))
                return redirect(request.path)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    key = _month(request)
    grid = svc.month_grid(member, key)
    first, _last = svc.month_bounds(key)
    lead = [None] * first.weekday()
    eaten = sum(len(d["meals"]) for d in grid)
    charges = member.charges.select_related("invoice")[:12]
    due = sum(((c.invoice.total - c.invoice.amount_paid) for c in charges if c.invoice), 0)
    return render(request, "webapp/mess/member.html", {
        "member": member, "form": form, "leave_form": leave_form, "grid": lead + grid, "month": key,
        "prev": _shift(key, -1), "next": _shift(key, 1), "eaten": eaten, "leaves": member.leaves.all()[:20],
        "charges": charges, "due": due, "away_days": sum(1 for d in grid if d["leave"]),
        "weekdays": [_("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun")], "month_label": first,
        "refund_note": (_("Refund %(amount)s per day on the next bill for mess cuts of %(days)s+ days.") % {
            "amount": member.plan.leave_refund_per_day, "days": member.plan.min_leave_days})
        if member.plan.leave_refund_per_day else "",
    })


@mess_view
def mess_bills(request):
    company = request.company
    key = _month(request)
    if request.method == "POST":
        try:
            invoices = svc.generate_month(company=company, user=request.user, key=key)
            messages.success(request, _("%(n)s mess bills created.") % {"n": len(invoices)})
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(f"{request.path}?month={key}")
    due = []
    for member in svc.due_for_month(company, key):
        fee, refund, days = svc.amount_for(member, key)
        if fee > 0:
            due.append({"m": member, "fee": fee, "refund": refund, "days": days, "total": fee - refund})
    charges = MessCharge.objects.for_company(company).filter(period=key).select_related("member__customer", "invoice")
    totals = charges.aggregate(billed=Sum("amount"))
    collected = sum((c.invoice.amount_paid for c in charges if c.invoice), 0)
    return render(request, "webapp/mess/bills.html", {
        "month": key, "prev": _shift(key, -1), "next": _shift(key, 1), "due": due,
        "due_total": sum((d["total"] for d in due), 0), "charges": charges,
        "billed": totals["billed"] or 0, "collected": collected,
    })


@mess_view
def mess_dues(request):
    return render(request, "webapp/mess/dues.html", {"rows": svc.dues(request.company)})
