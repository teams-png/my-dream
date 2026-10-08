"""Public website: landing page, pricing and self-service sign-up."""
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.contrib.auth.hashers import make_password
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.accounts import signup_otp
from apps.accounts import services as account_services
from apps.accounts.models import LoginAttempt
from apps.modules.catalog import BUSINESS_TYPE_MAP, business_group
from apps.modules.models import BusinessType, Module
from apps.subscriptions.models import SubscriptionPlan
from apps.subscriptions.pricing import CURRENCY_BY_COUNTRY, LARGE_BUSINESS_TYPES, fx_rates, is_exact, plans_for
from apps.subscriptions.services import TRIAL_DAYS
from apps.tenants.models import Company, CompanyBusinessType
from apps.webapp.guide_views import support_details

POPULAR_TYPES = [
    ("restaurant", "Restaurant / Cafe", "🍽️"), ("supermarket", "Supermarket", "🛒"),
    ("ladies_fashion_boutique", "Boutique", "👗"), ("mobile_shop", "Mobile Shop", "📱"),
    ("medical_shop", "Pharmacy", "💊"), ("saloon", "Salon / Barber", "💈"),
    ("gym", "Gym", "🏋️"), ("spa", "Spa", "🧖"), ("electronics_store", "Electronics", "🔌"),
    ("vehicle_wash", "Car Wash", "🚗"), ("construction", "Construction", "🏗️"), ("bakery", "Bakery", "🥐"),
]

COUNTRIES = ["Qatar", "United Arab Emirates", "Saudi Arabia", "Oman", "Kuwait", "Bahrain", "India",
             "United Kingdom", "United States", "Canada", "Australia", "Germany", "France", "Ireland",
             "Netherlands", "Italy", "Spain", "Other"]


def _business_choices():
    groups = {"restaurant": "Restaurant & food", "retail": "Shops & retail", "service": "Services",
              "project": "Projects & contracting"}
    grouped = {}
    for code, name in sorted(BUSINESS_TYPE_MAP.items(), key=lambda kv: kv[1]):
        group = business_group(code)
        grouped.setdefault(groups.get(group, "Specialised businesses"), []).append((code, name))
    return [(label, items) for label, items in grouped.items()]


class SignupForm(forms.Form):
    business_name = forms.CharField(max_length=120)
    business_type = forms.ChoiceField(choices=())
    country = forms.ChoiceField(choices=[(c, c) for c in COUNTRIES])
    full_name = forms.CharField(max_length=120)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, required=False)
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    plan = forms.ModelChoiceField(queryset=SubscriptionPlan.objects.none(), required=False)
    accept_terms = forms.BooleanField()
    website = forms.CharField(required=False)  # honeypot: humans never fill this

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_type"].choices = _business_choices()
        self.fields["plan"].queryset = SubscriptionPlan.objects.filter(is_active=True)
        self.fields["phone"].required = signup_otp.method() == "sms"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Please sign in instead.")
        return email

    def clean_password(self):
        from django.contrib.auth.password_validation import validate_password
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("phone") and signup_otp.method() == "sms":
            number = signup_otp.normalize(cleaned["phone"], cleaned.get("country", ""))
            if not number:
                self.add_error("phone", _("Enter a valid mobile number with the country code, e.g. +91 98475 54224."))
            elif get_user_model().objects.filter(phone=number, phone_verified=True).exists():
                self.add_error("phone", _("An account with this mobile number already exists. Please sign in instead."))
            else:
                cleaned["phone"] = number
        if cleaned.get("website"):
            raise forms.ValidationError("Sign-up could not be completed.")
        plan = cleaned.get("plan")
        if plan and cleaned.get("country") and cleaned.get("business_type"):
            if not plans_for(cleaned["country"], cleaned["business_type"]).filter(pk=plan.pk).exists():
                # e.g. an India price picked with Qatar as the country: use the matching plan instead
                cleaned["plan"] = plans_for(cleaned["country"], cleaned["business_type"]).filter(
                    max_users=plan.max_users).first()
        return cleaned


def _plans():
    return list(SubscriptionPlan.objects.filter(is_active=True).order_by("country", "tier", "max_users", "price"))


def _pricing_data():
    """Everything the pricing cards need to switch region, tier and display currency in the browser."""
    return {
        "plans": [{"id": p.id, "region": p.country, "tier": p.tier, "users": p.max_users, "name": p.name,
                   "price": f"{p.price:.2f}", "currency": p.currency, "period": p.billing_period,
                   "branches": p.max_warehouses, "extra_user": f"{p.extra_user_price:.0f}" if p.extra_user_price else "",
                   "extra_branch": f"{p.extra_branch_price:.0f}" if p.extra_branch_price else ""} for p in _plans()],
        "large_types": sorted(LARGE_BUSINESS_TYPES),
        "fx": {code: {"rate": str(rate), "exact": is_exact(code)} for code, rate in fx_rates().items()},
        "country_currency": CURRENCY_BY_COUNTRY,
    }


def landing(request):
    return render(request, "webapp/public/landing.html", {
        "plans": _plans(), "pricing": _pricing_data(), "popular_types": POPULAR_TYPES, "trial_days": TRIAL_DAYS,
        "business_count": len(BUSINESS_TYPE_MAP), "signup_enabled": settings.PUBLIC_SIGNUP_ENABLED,
        "module_count": Module.objects.count(), "support": support_details(),
    })


@transaction.atomic
def create_trial_account(*, data):
    from apps.tenants.services import create_company_with_owner, provision_company_basics
    User = get_user_model()
    first, _, last = data["full_name"].strip().partition(" ")
    user = User.objects.create_user(
        username=data["email"], email=data["email"], password=data.get("password"),
        first_name=first[:150], last_name=last[:150], phone=data.get("phone", ""),
        phone_verified=data.get("phone_verified", False), email_verified=data.get("email_verified", False),
    )
    if data.get("password_hash"):  # sign-up waited for the SMS code: the password was kept only as a hash
        user.password = data["password_hash"]
        user.save(update_fields=["password"])
    code = data["business_type"]
    business_type, _ = BusinessType.objects.get_or_create(code=code, defaults={"name": BUSINESS_TYPE_MAP.get(code, code)})
    base_slug = slugify(data["business_name"])[:40] or "business"
    slug, n = base_slug, 1
    while Company.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base_slug}-{n}"
    company = create_company_with_owner(
        user=user, name=data["business_name"].strip(), slug=slug, business_type=business_type,
        country=data["country"], phone=data.get("phone", ""), email=data["email"],
        default_currency=CURRENCY_BY_COUNTRY.get(data["country"], "USD"),
        plan=data.get("plan") or plans_for(data["country"], code).first(),
    )
    CompanyBusinessType.objects.update_or_create(
        company=company, business_type=business_type, defaults={"is_active": True, "is_primary": True},
    )
    provision_company_basics(company=company)
    return user, company


PENDING = "pending_signup"


def _signup_limited(request):
    ip_address = account_services.client_ip(request)
    recent = LoginAttempt.objects.filter(
        identifier="signup", ip_address=ip_address, attempted_at__gte=timezone.now() - timedelta(hours=1),
    ).count()
    return recent >= settings.SIGNUP_LIMIT_PER_IP_PER_HOUR


def _finish_signup(request, data):
    """Create the account, sign the person in and open the setup wizard."""
    LoginAttempt.objects.create(identifier="signup", ip_address=account_services.client_ip(request), successful=True)
    try:
        user, company = create_trial_account(data=data)
    except Exception as exc:
        messages.error(request, f"We could not create your account: {exc}")
        return None
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["active_company_id"] = company.id
    messages.success(request, f"Welcome to BookPilot! Your {TRIAL_DAYS}-day free trial has started.")
    return redirect("webapp:setup", step="business")


def _send_code(request, to):
    """Send a sign-up code, at most SIGNUP_OTP_SENDS_PER_HOUR per address and per network. Returns an error or None."""
    since = timezone.now() - timedelta(hours=1)
    ip_address = account_services.client_ip(request)
    limit = settings.SIGNUP_OTP_SENDS_PER_HOUR
    sent = LoginAttempt.objects.filter(attempted_at__gte=since, identifier__startswith="otp-send")
    if sent.filter(identifier=f"otp-send:{to}").count() >= limit or \
            sent.filter(ip_address=ip_address).count() >= limit * 2:
        return _("Too many codes were sent. Please wait an hour and try again.")
    try:
        signup_otp.send(to, request.session)
    except signup_otp.OtpError as exc:
        return str(exc)
    LoginAttempt.objects.create(identifier=f"otp-send:{to}", ip_address=ip_address, successful=True)
    request.session["otp_sent_at"] = timezone.now().timestamp()
    request.session["otp_tries"] = 0
    return None


def signup(request):
    if request.user.is_authenticated:
        return redirect("webapp:dashboard")
    if not settings.PUBLIC_SIGNUP_ENABLED:
        messages.error(request, "New sign-ups are currently by invitation only. Please contact us.")
        return redirect("webapp:landing")
    initial = {}
    if request.GET.get("plan", "").isdigit():
        initial["plan"] = request.GET["plan"]
    if request.GET.get("type") in BUSINESS_TYPE_MAP:
        initial["business_type"] = request.GET["type"]
    pending = request.session.get(PENDING)
    if pending and request.GET.get("edit"):  # "change number" from the code page: keep what was typed
        initial.update({k: v for k, v in pending.items() if k in SignupForm.base_fields and k != "password"})
    form = SignupForm(request.POST or None, initial=initial)
    if request.method == "POST":
        if _signup_limited(request):
            messages.error(request, "Too many sign-ups from this network. Please try again later.")
        elif form.is_valid():
            data = dict(form.cleaned_data)
            if not signup_otp.enabled():
                response = _finish_signup(request, data)
                if response:
                    return response
            else:
                plan = data.pop("plan")
                data.update(plan_id=plan.pk if plan else None, password_hash=make_password(data.pop("password")))
                request.session[PENDING] = data
                error = _send_code(request, signup_otp.target(data))
                if error:
                    messages.error(request, error)
                return redirect("webapp:signup_verify")
    return render(request, "webapp/public/signup.html", {
        "form": form, "plans": _plans(), "pricing": _pricing_data(), "trial_days": TRIAL_DAYS, "popular_types": POPULAR_TYPES,
        "otp": signup_otp.method(),
    })


def signup_verify(request):
    """Step 2 of sign-up: type the code we emailed (or sent by SMS)."""
    data = request.session.get(PENDING)
    if request.user.is_authenticated:
        return redirect("webapp:dashboard")
    if not data or not signup_otp.enabled():
        return redirect("webapp:signup")
    wait = max(0, int(60 - (timezone.now().timestamp() - request.session.get("otp_sent_at", 0))))
    if request.method == "POST":
        if request.POST.get("action") == "resend":
            if wait:
                messages.error(request, _("Please wait %(s)s seconds before asking for a new code.") % {"s": wait})
            else:
                error = _send_code(request, signup_otp.target(data))
                if error:
                    messages.error(request, error)
                else:
                    messages.success(request, _("A new code is on its way."))
            return redirect("webapp:signup_verify")
        tries = request.session.get("otp_tries", 0) + 1
        request.session["otp_tries"] = tries
        if tries > 5:
            messages.error(request, _("Too many wrong codes. Ask for a new code."))
        else:
            try:
                ok = signup_otp.check(signup_otp.target(data), request.POST.get("code"), request.session)
            except signup_otp.OtpError as exc:
                ok = False
                messages.error(request, str(exc))
            else:
                if not ok:
                    messages.error(request, _("That code is not right, or it has expired. Try again."))
            if ok:
                if get_user_model().objects.filter(email__iexact=data["email"]).exists():
                    messages.error(request, "An account with this email already exists. Please sign in instead.")
                    return redirect("webapp:login")
                if _signup_limited(request):
                    messages.error(request, "Too many sign-ups from this network. Please try again later.")
                    return redirect("webapp:signup_verify")
                plan = SubscriptionPlan.objects.filter(pk=data.get("plan_id"), is_active=True).first()
                sms = signup_otp.method() == "sms"
                response = _finish_signup(request, {**data, "plan": plan, "phone_verified": sms, "email_verified": not sms})
                for key in (PENDING, "otp_sent_at", "otp_tries", "otp_hash", "otp_made_at"):
                    request.session.pop(key, None)
                return response or redirect("webapp:signup")
        return redirect("webapp:signup_verify")
    return render(request, "webapp/public/signup_verify.html", {
        "to": signup_otp.masked(signup_otp.target(data)), "by_sms": signup_otp.method() == "sms",
        "wait": wait, "trial_days": TRIAL_DAYS,
    })


def home(request):
    """Visitors see the website; signed-in users go straight to their dashboard."""
    if not request.user.is_authenticated:
        # the installed web app and the desktop / mobile apps open on sign-in, not the website
        if request.GET.get("source") == "app" or "BookPilotApp" in request.META.get("HTTP_USER_AGENT", ""):
            return redirect("webapp:login")
        return landing(request)
    from .views import dashboard
    return dashboard(request)
