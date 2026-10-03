"""Public website: landing page, pricing and self-service sign-up."""
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts import services as account_services
from apps.accounts.models import LoginAttempt
from apps.modules.catalog import BUSINESS_TYPE_MAP, business_group
from apps.modules.models import BusinessType, Module
from apps.subscriptions.models import SubscriptionPlan
from apps.subscriptions.pricing import CURRENCY_BY_COUNTRY, LARGE_BUSINESS_TYPES, fx_rates, is_exact, plans_for
from apps.subscriptions.services import TRIAL_DAYS
from apps.tenants.models import Company, CompanyBusinessType

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
        "module_count": Module.objects.count(),
    })


@transaction.atomic
def create_trial_account(*, data):
    from apps.tenants.services import create_company_with_owner, provision_company_basics
    User = get_user_model()
    first, _, last = data["full_name"].strip().partition(" ")
    user = User.objects.create_user(
        username=data["email"], email=data["email"], password=data["password"],
        first_name=first[:150], last_name=last[:150], phone=data.get("phone", ""),
    )
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
    form = SignupForm(request.POST or None, initial=initial)
    if request.method == "POST":
        ip_address = account_services.client_ip(request)
        recent = LoginAttempt.objects.filter(
            identifier="signup", ip_address=ip_address, attempted_at__gte=timezone.now() - timedelta(hours=1),
        ).count()
        if recent >= settings.SIGNUP_LIMIT_PER_IP_PER_HOUR:
            messages.error(request, "Too many sign-ups from this network. Please try again later.")
        elif form.is_valid():
            LoginAttempt.objects.create(identifier="signup", ip_address=ip_address, successful=True)
            try:
                user, company = create_trial_account(data=form.cleaned_data)
            except Exception as exc:
                messages.error(request, f"We could not create your account: {exc}")
            else:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                request.session["active_company_id"] = company.id
                messages.success(request, f"Welcome to BookPilot! Your {TRIAL_DAYS}-day free trial has started.")
                return redirect("webapp:setup", step="business")
    return render(request, "webapp/public/signup.html", {
        "form": form, "plans": _plans(), "pricing": _pricing_data(), "trial_days": TRIAL_DAYS, "popular_types": POPULAR_TYPES,
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
