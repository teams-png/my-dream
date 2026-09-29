from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils import timezone as tz
from django.conf import settings
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
from decimal import Decimal

from apps.accounts import services as account_services
from apps.inventory.models import ProductCategory, Product, Warehouse, Unit, Brand
from apps.customers.models import Customer
from apps.verticals.mobile_shop.models import (
    MobileUnit, MobileRepairJob, MobileRepairPart, MobileTradeIn,
    MobileWarrantyClaim, MobileInstallmentPlan, MobileInstallmentPayment,
)
from apps.verticals.mobile_shop import services as mobile_shop_services
from apps.verticals.gym.models import MembershipPlan, GymMember, Attendance
from apps.verticals.gym import services as gym_services
from apps.verticals.spa.models import SpaService, Appointment
from apps.verticals.spa import services as spa_services
from apps.employees.models import Employee
from apps.modules.models import BusinessType, BusinessTypeDefaultModule
from apps.platform_admin.models import SupportTicket, PaymentGatewaySettings
from apps.platform_admin.payment_gateways import get_payment_gateway_config
from apps.audit.models import AuditLog
from django.contrib.auth import get_user_model
from apps.verticals.textile.models import FabricDetail, Measurement, TailoringOrder
from apps.verticals.textile import services as textile_services
from apps.verticals.vehicle_wash.models import Vehicle, WashPackage, WashOrder
from apps.verticals.vehicle_wash import services as wash_services
from apps.verticals.sports_shop.models import SportsProductDetail
from apps.verticals.cycle_shop.models import CycleUnit, ServiceTicket
from apps.verticals.cycle_shop import services as cycle_services
from apps.verticals.saloon.models import SaloonService, ServicePackage as SaloonServicePackage, CustomerPackage as SaloonCustomerPackage, Appointment as SaloonAppointment, ServiceClientProfile, ServiceCase, ServiceCaseNote
from apps.verticals.saloon import services as saloon_services
from apps.verticals.beauty_parlour.models import BeautyService, Appointment as BeautyAppointment
from apps.verticals.beauty_parlour import services as beauty_services
from apps.verticals.medical_shop.models import MedicineBatch, DispenseRecord
from apps.verticals.medical_shop import services as medical_services
from apps.verticals.protein_shop.models import ProteinBatch, SaleRecord
from apps.verticals.protein_shop import services as protein_services
from apps.verticals.restaurant.models import DiningArea, DiningTable, FoodWaste, KitchenStation, KitchenTicket, MenuModifier, MenuModifierGroup, MenuModifierOption, RestaurantMenuItem, RestaurantProfile, RestaurantOrderLine, RecipeIngredient, RestaurantCombo, RestaurantComboItem, RestaurantOrder, RestaurantShift, TableReservation, DeliveryIntegration, DeliveryOrderImport
from apps.verticals.restaurant import services as restaurant_services
from apps.verticals.construction.models import Project, Contractor, ProjectExpense, ProjectMilestone, ProjectTask, ProjectTimesheet
from apps.verticals.construction import services as construction_services
from apps.suppliers.models import Supplier
from apps.purchases.models import Purchase, PurchaseLine, SupplierPayment
from apps.purchases import services as purchase_services
from apps.sales.models import SalesInvoice, SalesInvoiceLine, SalesReturn, SalesReturnLine
from apps.sales import services as sales_services
from apps.expenses.models import ExpenseCategory, Expense
from apps.expenses import services as expense_services
from apps.tenants.models import Role, Permission, CompanyMembership, Company, CompanyBusinessType
from apps.subscriptions.models import Subscription, SubscriptionPlan, SubscriptionPayment
from apps.modules.models import Module, CompanyModule
from apps.modules.catalog import business_group, BUSINESS_TYPE_MAP, BUSINESS_TYPE_CHOICES
from .forms import WEB_FEATURES
from apps.tenants import services as tenant_services
from apps.sales.models import Coupon
from apps.customers.models import LoyaltyAccount, LoyaltyTransaction
from apps.customers import services as customer_services
from apps.notifications.models import Notification
from apps.notifications import services as notification_services
from functools import wraps
from .forms import (
    CategoryForm, ProductForm, MobileProductForm, BusinessProductForm, MobileUnitForm, MobileBulkIMEIForm,
    MobileRepairJobForm, MobileRepairPartForm, MobileWarrantyClaimForm, MobileTradeInForm,
    MobileInstallmentPaymentForm, CustomerForm, SellUnitForm,
    MembershipPlanForm, EnrollMemberForm, RenewMemberForm, SpaServiceForm, EmployeeForm, BookAppointmentForm,
    RegisterClientForm, FabricForm, MeasurementForm, TailoringOrderForm,
    VehicleForm, WashPackageForm, BookWashForm,
    SportsProductForm, CycleUnitForm, SellCycleForm, ServiceTicketForm,
    SaloonServiceForm, BookSaloonAppointmentForm, ServiceClientProfileForm, ServiceCaseForm, ServiceCaseNoteForm,
    SaloonServicePackageForm, SaloonPackagePurchaseForm,
    BeautyServiceForm, BookBeautyAppointmentForm,
    MedicineBatchForm, DispenseForm, ProteinBatchForm, SellProteinForm,
    ProjectForm, ContractorForm, ProjectExpenseForm, ProjectMilestoneForm, ProjectTaskForm, ProjectTimesheetForm,
    RetailSaleForm, UnitForm,
    BrandForm, VariantForm, SupplierForm, PurchaseForm, SupplierPaymentForm,
    InvoiceLookupForm, SalesReturnForm, ExpenseCategoryForm, ExpenseForm,
    InviteStaffForm, ChangeMemberRoleForm, CustomRoleForm, CouponForm, RedeemPointsForm,
    CompanySettingsForm, BranchForm, ProductImportForm, EditUserCredentialsForm,
    SubscriptionPlanForm, BillingPaymentForm,
    PlatformModuleForm, PlatformBusinessTypeForm, PlatformSupportTicketForm, PaymentGatewaySettingsForm,
    DiningAreaForm, DiningTableForm, RestaurantOrderForm, RestaurantOrderLineForm,
    RestaurantSettleForm, RestaurantShiftOpenForm, RestaurantShiftCloseForm,
    MenuModifierForm, MenuModifierGroupForm, MenuModifierOptionForm, RestaurantMenuItemForm, RestaurantProfileForm, RecipeIngredientForm, RestaurantComboForm, RestaurantComboItemForm,
    FoodWasteForm, KitchenStationForm, TableReservationForm,
    DeliveryIntegrationForm,
)
from apps.subscriptions import services as subscription_services


def require_permission(code):
    """Blocks the view unless request.role has the given permission code.
    Falls back to allow-all if the company has no roles configured yet
    (shouldn't happen post-signup, but avoids locking an owner out)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            role = getattr(request, "role", None)
            if role is not None and not role.permissions.filter(permission__code=code).exists():
                messages.error(request, "You don't have permission to do that.")
                return redirect("webapp:dashboard")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def require_business_group(*allowed):
    """Prevents a tenant from opening another industry's workflow by guessing its URL."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            company = getattr(request, "company", None)
            groups = set()
            if company:
                groups.add(business_group(company.business_type.code))
                groups.update(business_group(code) for code in company.business_suites.filter(is_active=True).values_list("business_type__code", flat=True))
            if not groups.intersection(allowed):
                messages.error(request, "This workflow is not enabled for your business type.")
                return redirect("webapp:dashboard")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def has_feature(company, code):
    """True if this webapp feature hasn't been disabled by the platform admin
    for this company. Defaults to enabled if no row exists at all (e.g. a
    company created before this feature toggle existed)."""
    if company is None:
        return False
    return not CompanyModule.objects.filter(company=company, module__code=code, is_active=False).exists()


def require_feature(code):
    """Hard-blocks the view (not just hides the nav link) if a platform admin
    has disabled this feature for the company — defense in depth alongside
    the nav-level hiding in base.html."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            company = getattr(request, "company", None)
            if not getattr(request.user, "is_platform_admin", False) and not has_feature(company, code):
                messages.error(request, "This feature isn't enabled for your account. Contact support.")
                return redirect("webapp:dashboard")
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def login_view(request):
    if request.user.is_authenticated:
        return redirect("webapp:platform_admin_dashboard" if request.user.is_platform_admin else "webapp:dashboard")

    if request.method == "POST":
        identifier = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        ip_address = account_services.client_ip(request)

        if account_services.is_locked_out(identifier, ip_address):
            messages.error(request, "Too many failed attempts. Try again later.")
            return render(request, "webapp/login.html")

        user = authenticate(request, username=identifier, password=password)
        account_services.record_attempt(identifier, ip_address, successful=user is not None)

        if user is not None:
            login(request, user)
            return redirect("webapp:platform_admin_dashboard" if user.is_platform_admin else "webapp:dashboard")
        messages.error(request, "Invalid username or password.")

    return render(request, "webapp/login.html")


def logout_view(request):
    logout(request)
    return redirect("webapp:login")


@login_required
def switch_company(request, company_id):
    membership = request.user.memberships.filter(
        company_id=company_id, is_active=True, company__is_active=True
    ).first()
    if membership is None:
        messages.error(request, "You don't have access to that company.")
    else:
        request.session["active_company_id"] = membership.company_id
        messages.success(request, f"Switched to {membership.company.name}.")
    return redirect("webapp:dashboard")


@login_required
def dashboard(request):
    if request.user.is_platform_admin:
        return redirect("webapp:platform_admin_dashboard")

    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    biz_code = getattr(company.business_type, "code", None)
    subscription = Subscription.objects.filter(company=company).select_related("plan").first()
    context = {
        "company": company, "customer_count": Customer.objects.for_company(company).count(),
        "subscription": subscription,
        "subscription_days_left": subscription.days_remaining() if subscription else None,
    }

    if biz_code in ("gym", "fitness_center"):
        members = GymMember.objects.for_company(company)
        context.update({
            "plan_count": MembershipPlan.objects.for_company(company).count(),
            "active_member_count": members.filter(status="active").count(),
            "member_count": members.count(),
        })
    elif biz_code == "spa":
        appts = Appointment.objects.for_company(company)
        today = tz.now().date()
        context.update({
            "service_count": SpaService.objects.for_company(company).count(),
            "today_appt_count": appts.filter(scheduled_at__date=today).count(),
            "completed_count": appts.filter(status="completed").count(),
        })
    elif biz_code in ("textile", "tailoring_shop"):
        orders = TailoringOrder.objects.for_company(company)
        context.update({
            "fabric_count": FabricDetail.objects.for_company(company).count(),
            "pending_count": orders.filter(status__in=["pending", "in_progress"]).count(),
            "ready_count": orders.filter(status="ready").count(),
        })
    elif biz_code in ("vehicle_wash", "car_wash"):
        orders = WashOrder.objects.for_company(company)
        completed = orders.filter(status="completed")
        context.update({
            "vehicle_count": Vehicle.objects.for_company(company).count(),
            "today_count": orders.filter(scheduled_at__date=tz.now().date()).count(),
            "revenue": completed.aggregate(total=Sum("price"))["total"] or 0,
        })
    elif biz_code in ("sports_shop", "fitness_sports_store"):
        context.update({
            "product_count": Product.objects.for_company(company).count(),
            "category_count": ProductCategory.objects.for_company(company).count(),
        })
    elif biz_code == "cycle_shop":
        units = CycleUnit.objects.for_company(company)
        tickets = ServiceTicket.objects.for_company(company)
        context.update({
            "in_stock_count": units.filter(status="in_stock").count(),
            "sold_count": units.filter(status="sold").count(),
            "open_tickets": tickets.exclude(status="delivered").count(),
        })
    elif biz_code in ("saloon", "barber_shop"):
        appts = SaloonAppointment.objects.for_company(company)
        context.update({
            "service_count": SaloonService.objects.for_company(company).count(),
            "today_appt_count": appts.filter(scheduled_at__date=tz.now().date()).count(),
            "completed_count": appts.filter(status="completed").count(),
        })
    elif biz_code in ("beauty_parlour", "beauty_salon"):
        appts = BeautyAppointment.objects.for_company(company)
        context.update({
            "service_count": BeautyService.objects.for_company(company).count(),
            "today_appt_count": appts.filter(scheduled_at__date=tz.now().date()).count(),
            "completed_count": appts.filter(status="completed").count(),
        })
    elif biz_code in ("medical_shop", "pharmacy"):
        batches = MedicineBatch.objects.for_company(company)
        context.update({
            "batch_count": batches.filter(quantity_remaining__gt=0).count(),
            "expiring_soon": sum(1 for b in batches if 0 <= (b.expiry_date - tz.now().date()).days <= 30),
        })
    elif biz_code == "protein_shop":
        batches = ProteinBatch.objects.for_company(company)
        context.update({
            "batch_count": batches.filter(quantity_remaining__gt=0).count(),
            "expiring_soon": sum(1 for b in batches if 0 <= (b.expiry_date - tz.now().date()).days <= 30),
        })
    elif biz_code in ("construction", "contracting_company"):
        projects = Project.objects.for_company(company)
        context.update({
            "active_projects": projects.filter(status="active").count(),
            "total_projects": projects.count(),
        })
    elif biz_code in (
        "general_retail", "watch_shop", "perfume_shop", "book_store",
        "retail_shop", "supermarket", "grocery_store", "clothing_store", "ladies_fashion_boutique", "electronics_store",
        "computer_shop", "furniture_store", "hardware_store", "cosmetics_store", "jewelry_shop",
        "auto_spare_parts", "medical_equipment_store", "flower_shop", "pet_shop", "bakery",
        "trading_company", "wholesale_business", "import_export",
        "car_showroom", "printing_shop", "manufacturing", "industrial_services",
    ):
        invoices = SalesInvoice.objects.for_company(company)
        context.update({
            "product_count": Product.objects.for_company(company).count(),
            "category_count": ProductCategory.objects.for_company(company).count(),
            "invoice_count": invoices.count(),
            "revenue": invoices.aggregate(total=Sum("total"))["total"] or 0,
        })
    elif biz_code in (
        "dental_clinic", "medical_clinic", "physiotherapy_center", "veterinary_clinic",
        "photography_studio", "driving_school", "tuition_center", "consultancy",
        "auto_garage", "repair_services", "home_services", "laundry_dry_cleaning",
    ):
        appts = SaloonAppointment.objects.for_company(company)
        context.update({
            "service_count": SaloonService.objects.for_company(company).count(),
            "today_appt_count": appts.filter(scheduled_at__date=tz.now().date()).count(),
            "completed_count": appts.filter(status="completed").count(),
        })
    elif biz_code in (
        "advertising_agency", "digital_marketing_agency", "web_development", "it_services",
        "software_company", "accounting_audit", "recruitment_agency", "security_services",
        "event_management", "cleaning_company", "maintenance_company", "landscaping_company",
    ):
        projects = Project.objects.for_company(company)
        context.update({
            "active_projects": projects.filter(status="active").count(),
            "total_projects": projects.count(),
        })
    else:
        sold_units = MobileUnit.objects.for_company(company).filter(status="sold")
        context.update({
            "category_count": ProductCategory.objects.for_company(company).count(),
            "product_count": Product.objects.for_company(company).count(),
            "unit_count": MobileUnit.objects.for_company(company).filter(status="in_stock").count(),
            "sales_count": sold_units.count(),
            "revenue": sold_units.aggregate(total=Sum("sold_price"))["total"] or 0,
        })

    # Universal, vertical-independent widgets — every company has sales, expenses
    # and customers regardless of business type, so these render on every dashboard.
    today = tz.now().date()
    month_start = today.replace(day=1)
    invoices_all = SalesInvoice.objects.for_company(company).exclude(status="void")
    today_sales = invoices_all.filter(date=today).aggregate(t=Sum("total"))["t"] or 0
    month_revenue = invoices_all.filter(date__gte=month_start).aggregate(t=Sum("total"))["t"] or 0
    outstanding = invoices_all.aggregate(total=Sum("total"), paid=Sum("amount_paid"))
    outstanding_dues = (outstanding["total"] or 0) - (outstanding["paid"] or 0)
    low_stock_count = sum(
        1 for p in Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True)
        if p.current_stock() <= p.reorder_level
    )
    recent_invoices = invoices_all.select_related("customer").order_by("-date", "-id")[:6]

    context.update({
        "today_sales": today_sales,
        "month_revenue": month_revenue,
        "outstanding_dues": outstanding_dues,
        "low_stock_count": low_stock_count,
        "recent_invoices": recent_invoices,
    })
    return render(request, "webapp/dashboard.html", context)


# ---------- Units ----------

@login_required
def inventory_unit_list(request):
    company = request.company
    units = Unit.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/unit_list.html", {"units": units})


@login_required
def inventory_unit_add(request):
    company = request.company
    if request.method == "POST":
        form = UnitForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Unit added.")
            return redirect("webapp:inventory_unit_list")
    else:
        form = UnitForm()
    return render(request, "webapp/unit_form.html", {"form": form})


@login_required
def inventory_unit_delete(request, unit_id):
    company = request.company
    obj = get_object_or_404(Unit.objects.for_company(company), id=unit_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Unit deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this unit is used by existing products.")
        return redirect("webapp:inventory_unit_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:inventory_unit_list", "delete_url": "webapp:inventory_unit_delete", "delete_id": unit_id,
    })


# ---------- Brands ----------

@login_required
def brand_list(request):
    company = request.company
    brands = Brand.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/brand_list.html", {"brands": brands})


@login_required
def brand_add(request):
    company = request.company
    if request.method == "POST":
        form = BrandForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Brand added.")
            return redirect("webapp:brand_list")
    else:
        form = BrandForm()
    return render(request, "webapp/brand_form.html", {"form": form})


@login_required
def brand_delete(request, brand_id):
    company = request.company
    obj = get_object_or_404(Brand.objects.for_company(company), id=brand_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Brand deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this brand is used by existing products.")
        return redirect("webapp:brand_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:brand_list", "delete_url": "webapp:brand_delete", "delete_id": brand_id,
    })


# ---------- Categories ----------

@login_required
def category_list(request):
    company = request.company
    categories = ProductCategory.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/mobile_shop/category_list.html", {"categories": categories})


@login_required
def category_add(request):
    company = request.company
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Category added.")
            return redirect("webapp:category_list")
    else:
        form = CategoryForm()
    return render(request, "webapp/mobile_shop/category_form.html", {"form": form})


@login_required
def category_edit(request, category_id):
    company = request.company
    obj = get_object_or_404(ProductCategory.objects.for_company(company), id=category_id)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated.")
            return redirect("webapp:category_list")
    else:
        form = CategoryForm(instance=obj)
    return render(request, "webapp/mobile_shop/category_form.html", {"form": form, "editing": True})


@login_required
def category_delete(request, category_id):
    company = request.company
    obj = get_object_or_404(ProductCategory.objects.for_company(company), id=category_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Category deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this category is used by existing products.")
        return redirect("webapp:category_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:category_list", "delete_url": "webapp:category_delete", "delete_id": category_id,
    })


# ---------- Products ----------

@login_required
def product_list(request):
    company = request.company
    products = (
        Product.objects.for_company(company).filter(parent__isnull=True)
        .select_related("category", "brand", "unit").prefetch_related("variants")
        .order_by("name")
        if company else []
    )
    return render(request, "webapp/mobile_shop/product_list.html", {"products": products})


@login_required
def product_add(request):
    company = request.company
    if company and company.business_type.code == "mobile_shop":
        form_class = MobileProductForm
    elif company and business_group(company.business_type.code) == "retail":
        form_class = BusinessProductForm
    else:
        form_class = ProductForm
    if request.method == "POST":
        form = form_class(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Product added.")
            return redirect("webapp:product_list")
    else:
        form = form_class(company=company)
    return render(request, "webapp/mobile_shop/product_form.html", {"form": form})


@login_required
def product_edit(request, product_id):
    company = request.company
    obj = get_object_or_404(Product.objects.for_company(company), id=product_id)
    if company and company.business_type.code == "mobile_shop":
        form_class = MobileProductForm
    elif company and business_group(company.business_type.code) == "retail":
        form_class = BusinessProductForm
    else:
        form_class = ProductForm
    if request.method == "POST":
        form = form_class(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Product updated.")
            return redirect("webapp:product_list")
    else:
        form = form_class(instance=obj, company=company)
    return render(request, "webapp/mobile_shop/product_form.html", {"form": form, "editing": True})


@login_required
def product_delete(request, product_id):
    company = request.company
    obj = get_object_or_404(Product.objects.for_company(company), id=product_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Product deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this product has sales, stock, or other records linked to it.")
        return redirect("webapp:product_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:product_list", "delete_url": "webapp:product_delete", "delete_id": product_id,
    })


@login_required
def product_variant_add(request, product_id):
    company = request.company
    parent = get_object_or_404(Product.objects.for_company(company), id=product_id)
    if request.method == "POST":
        form = VariantForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            Product.objects.create(
                company=company, sku=d["sku"], name=parent.name, category=parent.category, brand=parent.brand,
                unit=parent.unit, cost_price=d["cost_price"], selling_price=d["selling_price"],
                parent=parent, variant_label=d["variant_label"], size=d["size"], colour=d["colour"],
                material=d["material"] or parent.material, design=d["design"] or parent.design,
            )
            messages.success(request, "Variant added.")
            return redirect("webapp:product_list")
    else:
        form = VariantForm(initial={"cost_price": parent.cost_price, "selling_price": parent.selling_price})
    return render(request, "webapp/mobile_shop/variant_form.html", {"form": form, "parent": parent})


@login_required
def product_barcode(request, product_id):
    from django.http import HttpResponse

    company = request.company
    product = get_object_or_404(Product.objects.for_company(company), id=product_id)

    try:
        import barcode
        from barcode.writer import ImageWriter
        import io

        code = barcode.get("code128", product.sku, writer=ImageWriter())
        buf = io.BytesIO()
        code.write(buf, options={"write_text": True, "module_height": 12, "quiet_zone": 2})
        return HttpResponse(buf.getvalue(), content_type="image/png")
    except Exception as exc:
        return HttpResponse(f"Barcode unavailable: {exc}", content_type="text/plain", status=500)


@login_required
def barcode_print(request):
    company = request.company
    products = Product.objects.for_company(company).filter(is_active=True).order_by("name")

    if request.method == "POST":
        selected_ids = request.POST.getlist("product_ids")
        items = []
        for pid in selected_ids:
            qty = request.POST.get(f"qty_{pid}", "1")
            try:
                qty = max(1, int(qty))
            except (TypeError, ValueError):
                qty = 1
            product = Product.objects.for_company(company).filter(id=pid).first()
            if product:
                items.extend([product] * qty)
        return render(request, "webapp/barcode_print_sheet.html", {"items": items})

    return render(request, "webapp/barcode_print_select.html", {"products": products})


# ---------- Mobile Units ----------

@login_required
def unit_list(request):
    company = request.company
    units = MobileUnit.objects.for_company(company).select_related("product").order_by("-id") if company else []
    return render(request, "webapp/mobile_shop/unit_list.html", {"units": units})


@login_required
def unit_add(request):
    company = request.company
    if request.method == "POST":
        form = MobileUnitForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Unit added.")
            return redirect("webapp:unit_list")
    else:
        form = MobileUnitForm(company=company)
    return render(request, "webapp/mobile_shop/unit_form.html", {"form": form})


@login_required
@transaction.atomic
def mobile_bulk_imei_add(request):
    company = request.company
    if request.method == "POST":
        form = MobileBulkIMEIForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            rows = d["imeis"]
            duplicates = MobileUnit.objects.for_company(company).filter(imei__in=[r[0] for r in rows]).values_list("imei", flat=True)
            if duplicates:
                form.add_error("imeis", "Already registered: " + ", ".join(duplicates))
            else:
                purchase = None
                if d.get("supplier"):
                    purchase = purchase_services.create_purchase(
                        company=company, user=request.user, supplier=d["supplier"], date=tz.now().date(),
                        warehouse=d["warehouse"], bill_number=f"IMEI-{tz.now():%Y%m%d%H%M}",
                        lines=[{"product": d["product"], "quantity": Decimal(len(rows)), "unit_cost": d["purchase_price"]}],
                    )
                MobileUnit.objects.bulk_create([
                    MobileUnit(company=company, product=d["product"], warehouse=d["warehouse"], imei=imei,
                               serial_number=serial, condition=d["condition"], warranty_months=d["warranty_months"],
                               purchase_price=d["purchase_price"], status="in_stock")
                    for imei, serial in rows
                ])
                messages.success(request, f"{len(rows)} IMEI units added" + (" and purchase recorded." if purchase else "."))
                return redirect("webapp:unit_list")
    else:
        form = MobileBulkIMEIForm(company=company)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Bulk IMEI purchase / stock intake", "cancel_url": "webapp:unit_list"})


@login_required
def mobile_repair_list(request):
    jobs = MobileRepairJob.objects.for_company(request.company).select_related("customer", "assigned_technician", "mobile_unit").prefetch_related("parts").order_by("-received_at")
    return render(request, "webapp/mobile_shop/repair_list.html", {"jobs": jobs})


@login_required
def mobile_repair_form(request, job_id=None):
    company = request.company
    job = get_object_or_404(MobileRepairJob.objects.for_company(company), id=job_id) if job_id else None
    form = MobileRepairJobForm(request.POST or None, instance=job, company=company)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.company = company
        if not obj.job_number:
            from apps.tenants.services import next_counter_value
            obj.job_number = f"REP-{next_counter_value(company, 'mobile_repair'):06d}"
        if obj.status == "completed" and not obj.completed_at:
            obj.completed_at = tz.now()
        obj.save()
        messages.success(request, "Repair job saved.")
        return redirect("webapp:mobile_repair_detail", job_id=obj.id)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Repair job", "cancel_url": "webapp:mobile_repair_list"})


@login_required
def mobile_repair_detail(request, job_id):
    job = get_object_or_404(MobileRepairJob.objects.for_company(request.company).select_related("customer", "assigned_technician", "invoice"), id=job_id)
    return render(request, "webapp/mobile_shop/repair_detail.html", {"job": job, "parts": job.parts.select_related("product")})


@login_required
@transaction.atomic
def mobile_repair_part_add(request, job_id):
    company = request.company
    job = get_object_or_404(MobileRepairJob.objects.for_company(company), id=job_id)
    form = MobileRepairPartForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        part = form.save(commit=False)
        part.company, part.job = company, job
        part.save()
        from apps.inventory.services import record_stock_movement
        record_stock_movement(company=company, product=part.product, warehouse=job.warehouse,
                              quantity=-part.quantity, reason="sale", reference=job.job_number)
        job.parts_total = sum((p.line_total for p in job.parts.all()), Decimal("0"))
        job.save(update_fields=["parts_total"])
        messages.success(request, "Spare part added and stock deducted.")
        return redirect("webapp:mobile_repair_detail", job_id=job.id)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": f"Add spare part — {job.job_number}", "cancel_url": "webapp:mobile_repair_detail", "cancel_id": job.id})


@login_required
@transaction.atomic
def mobile_repair_complete(request, job_id):
    job = get_object_or_404(MobileRepairJob.objects.for_company(request.company), id=job_id)
    if request.method == "POST":
        labour = Decimal(request.POST.get("labour_cost") or 0)
        final = labour + job.parts_total
        mobile_shop_services.complete_repair_job(company=request.company, user=request.user, job=job,
            date=tz.now().date(), final_cost=final, work_done=request.POST.get("work_done", ""))
        job.labour_cost = labour
        job.save(update_fields=["labour_cost"])
        messages.success(request, "Repair completed and invoice created.")
    return redirect("webapp:mobile_repair_detail", job_id=job.id)


@login_required
def mobile_warranty_list(request):
    claims = MobileWarrantyClaim.objects.for_company(request.company).select_related("unit", "unit__product", "customer").order_by("-received_date")
    return render(request, "webapp/mobile_shop/warranty_list.html", {"claims": claims})


@login_required
def mobile_warranty_form(request, claim_id=None):
    company = request.company
    claim = get_object_or_404(MobileWarrantyClaim.objects.for_company(company), id=claim_id) if claim_id else None
    form = MobileWarrantyClaimForm(request.POST or None, instance=claim, company=company)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.company = company
        if not obj.claim_number:
            from apps.tenants.services import next_counter_value
            obj.claim_number = f"WAR-{next_counter_value(company, 'mobile_warranty'):06d}"
        obj.save()
        messages.success(request, "Warranty claim saved.")
        return redirect("webapp:mobile_warranty_list")
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Warranty claim", "cancel_url": "webapp:mobile_warranty_list"})


@login_required
def mobile_tradein_list(request):
    items = MobileTradeIn.objects.for_company(request.company).select_related("customer", "product", "mobile_unit").order_by("-created_at")
    return render(request, "webapp/mobile_shop/tradein_list.html", {"items": items})


@login_required
def mobile_tradein_add(request):
    form = MobileTradeInForm(request.POST or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.save()
        messages.success(request, "Trade-in quotation saved.")
        return redirect("webapp:mobile_tradein_list")
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "New trade-in / exchange", "cancel_url": "webapp:mobile_tradein_list"})


@login_required
def mobile_tradein_accept(request, trade_id):
    trade = get_object_or_404(MobileTradeIn.objects.for_company(request.company), id=trade_id)
    if request.method == "POST":
        mobile_shop_services.accept_trade_in(company=request.company, user=request.user, trade_in=trade, date=tz.now().date())
        messages.success(request, "Trade-in accepted; used handset added to stock.")
    return redirect("webapp:mobile_tradein_list")


@login_required
def mobile_installment_list(request):
    plans = MobileInstallmentPlan.objects.for_company(request.company).select_related("customer", "invoice").prefetch_related("payments").order_by("next_due_date")
    today = tz.now().date()
    MobileInstallmentPlan.objects.for_company(request.company).filter(status="active", next_due_date__lt=today).update(status="overdue")
    return render(request, "webapp/mobile_shop/installment_list.html", {"plans": plans})


@login_required
def mobile_installment_payment(request, plan_id):
    plan = get_object_or_404(MobileInstallmentPlan.objects.for_company(request.company), id=plan_id)
    form = MobileInstallmentPaymentForm(request.POST or None, initial={"date": tz.now().date()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        mobile_shop_services.record_installment_payment(company=request.company, user=request.user, plan=plan, **d)
        messages.success(request, "Instalment payment recorded.")
        return redirect("webapp:mobile_installment_list")
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": f"Collect instalment — {plan.invoice.invoice_number}", "cancel_url": "webapp:mobile_installment_list"})


# ---------- Customers ----------

@login_required
def customer_list(request):
    company = request.company
    customers = Customer.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/customer_list.html", {"customers": customers})


@login_required
def customer_add(request):
    company = request.company
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Customer added.")
            return redirect("webapp:customer_list")
    else:
        form = CustomerForm()
    return render(request, "webapp/customer_form.html", {"form": form})


@login_required
def customer_edit(request, customer_id):
    company = request.company
    obj = get_object_or_404(Customer.objects.for_company(company), id=customer_id)
    if request.method == "POST":
        form = CustomerForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Customer updated.")
            return redirect("webapp:customer_list")
    else:
        form = CustomerForm(instance=obj)
    return render(request, "webapp/customer_form.html", {"form": form, "editing": True})


@login_required
def customer_delete(request, customer_id):
    company = request.company
    obj = get_object_or_404(Customer.objects.for_company(company), id=customer_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Customer deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this customer has sales, appointments, or other records linked to them.")
        return redirect("webapp:customer_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:customer_list", "delete_url": "webapp:customer_delete", "delete_id": customer_id,
    })


# ---------- Sales ----------

@login_required
def sale_list(request):
    company = request.company
    sales = (
        MobileUnit.objects.for_company(company)
        .filter(status="sold")
        .select_related("product", "buyer")
        .order_by("-sold_date")
        if company else []
    )
    return render(request, "webapp/mobile_shop/sale_list.html", {"sales": sales})


@login_required
def sell_unit(request, unit_id):
    company = request.company
    unit = get_object_or_404(MobileUnit.objects.for_company(company), id=unit_id)

    if unit.status != "in_stock":
        messages.error(request, "This unit isn't available to sell.")
        return redirect("webapp:unit_list")

    if request.method == "POST":
        form = SellUnitForm(request.POST, company=company)
        if form.is_valid():
            mobile_shop_services.sell_unit(
                unit,
                company=company,
                user=request.user,
                warehouse=unit.warehouse or _default_warehouse(company),
                buyer=form.cleaned_data["buyer"],
                sold_price=form.cleaned_data["sold_price"],
                sold_date=form.cleaned_data["sold_date"],
            )
            messages.success(request, f"Sold {unit.product.name} (IMEI {unit.imei}).")
            return redirect("webapp:sale_list")
    else:
        form = SellUnitForm(initial={"sold_date": timezone.now().date()}, company=company)

    return render(request, "webapp/mobile_shop/sell_form.html", {"form": form, "unit": unit})


# ---------- Reports ----------

@login_required
def reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    start = request.GET.get("start")
    end = request.GET.get("end")
    sold_units = MobileUnit.objects.for_company(company).filter(status="sold")
    if start: sold_units = sold_units.filter(sold_date__gte=start)
    if end: sold_units = sold_units.filter(sold_date__lte=end)
    in_stock = MobileUnit.objects.for_company(company).filter(status="in_stock")

    top_products = (
        sold_units.values("product__name")
        .annotate(units_sold=Count("id"), revenue=Sum("sold_price"))
        .order_by("-revenue")[:8]
    )

    revenue = sold_units.aggregate(total=Sum("sold_price"))["total"] or Decimal("0")
    handset_cost = sold_units.aggregate(total=Sum("purchase_price"))["total"] or Decimal("0")
    repair_jobs = MobileRepairJob.objects.for_company(company).filter(status="completed")
    if start: repair_jobs = repair_jobs.filter(completed_at__date__gte=start)
    if end: repair_jobs = repair_jobs.filter(completed_at__date__lte=end)
    repair_income = repair_jobs.aggregate(t=Sum("final_cost"))["t"] or Decimal("0")
    accessory_lines = SalesInvoiceLine.objects.filter(invoice__company=company, invoice__status__in=["paid", "partial"], product__attributes__item_type__in=["accessory", "spare_part"])
    if start: accessory_lines = accessory_lines.filter(invoice__date__gte=start)
    if end: accessory_lines = accessory_lines.filter(invoice__date__lte=end)
    accessory_revenue = accessory_lines.aggregate(t=Sum("line_total"))["t"] or Decimal("0")
    accessory_cost = sum((line.quantity * line.product.cost_price for line in accessory_lines.select_related("product")), Decimal("0"))
    installment_plans = MobileInstallmentPlan.objects.for_company(company).exclude(status__in=["paid", "cancelled"])
    context = {
        "total_revenue": revenue + accessory_revenue + repair_income,
        "handset_revenue": revenue, "accessory_revenue": accessory_revenue, "repair_income": repair_income,
        "cost_of_goods": handset_cost + accessory_cost,
        "gross_profit": revenue + accessory_revenue + repair_income - handset_cost - accessory_cost,
        "units_sold": sold_units.count(),
        "units_in_stock": in_stock.count(),
        "stock_value": in_stock.aggregate(t=Sum("purchase_price"))["t"] or 0,
        "open_repairs": MobileRepairJob.objects.for_company(company).exclude(status__in=["completed", "cancelled"]).count(),
        "open_warranty": MobileWarrantyClaim.objects.for_company(company).exclude(status__in=["resolved", "rejected"]).count(),
        "outstanding_dues": sum((p.outstanding for p in installment_plans), Decimal("0")),
        "top_products": top_products,
        "start": start or "", "end": end or "",
    }
    return render(request, "webapp/mobile_shop/reports.html", context)


# ================= GYM =================

def _default_warehouse(company):
    wh = Warehouse.objects.for_company(company).filter(is_default=True).first()
    if wh is None:
        wh = Warehouse.objects.for_company(company).first()
    if wh is None:
        wh = Warehouse.objects.create(company=company, name="Main", is_default=True)
    return wh


def _selected_warehouse(company, warehouse_id):
    """Returns the requested branch/warehouse if it belongs to the company, else the default one."""
    if warehouse_id:
        wh = Warehouse.objects.for_company(company).filter(id=warehouse_id, is_active=True).first()
        if wh is not None:
            return wh
    return _default_warehouse(company)


@login_required
def plan_list(request):
    company = request.company
    plans = MembershipPlan.objects.for_company(company).order_by("price") if company else []
    return render(request, "webapp/gym/plan_list.html", {"plans": plans})


@login_required
def plan_add(request):
    company = request.company
    if request.method == "POST":
        form = MembershipPlanForm(request.POST)
        if form.is_valid():
            gym_services.create_membership_plan(
                company=company,
                name=form.cleaned_data["name"],
                duration_days=form.cleaned_data["duration_days"],
                price=form.cleaned_data["price"],
            )
            messages.success(request, "Membership plan added.")
            return redirect("webapp:plan_list")
    else:
        form = MembershipPlanForm()
    return render(request, "webapp/gym/plan_form.html", {"form": form})


@login_required
def plan_edit(request, plan_id):
    company = request.company
    obj = get_object_or_404(MembershipPlan.objects.for_company(company), id=plan_id)
    if request.method == "POST":
        form = MembershipPlanForm(request.POST)
        if form.is_valid():
            obj.name = form.cleaned_data["name"]
            obj.duration_days = form.cleaned_data["duration_days"]
            obj.price = form.cleaned_data["price"]
            obj.save()
            messages.success(request, "Plan updated.")
            return redirect("webapp:plan_list")
    else:
        form = MembershipPlanForm(initial={"name": obj.name, "duration_days": obj.duration_days, "price": obj.price})
    return render(request, "webapp/gym/plan_form.html", {"form": form, "editing": True})


@login_required
def plan_delete(request, plan_id):
    company = request.company
    obj = get_object_or_404(MembershipPlan.objects.for_company(company), id=plan_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Plan deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — members are enrolled in this plan.")
        return redirect("webapp:plan_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:plan_list", "delete_url": "webapp:plan_delete", "delete_id": plan_id,
    })


@login_required
def member_list(request):
    company = request.company
    members = (
        GymMember.objects.for_company(company).select_related("customer", "membership_plan").order_by("-join_date")
        if company else []
    )
    return render(request, "webapp/gym/member_list.html", {"members": members})


@login_required
def member_enroll(request):
    company = request.company
    if request.method == "POST":
        form = EnrollMemberForm(request.POST, company=company)
        if form.is_valid():
            try:
                gym_services.enroll_member(
                    company=company,
                    user=request.user,
                    customer=form.cleaned_data["customer"],
                    membership_plan=form.cleaned_data["membership_plan"],
                    join_date=form.cleaned_data["join_date"],
                    warehouse=_default_warehouse(company),
                )
                messages.success(request, "Member enrolled and invoiced.")
                return redirect("webapp:member_list")
            except Exception as exc:
                messages.error(request, f"Couldn't enroll member: {exc}")
    else:
        form = EnrollMemberForm(company=company, initial={"join_date": tz.now().date()})

    no_plans = not MembershipPlan.objects.for_company(company).filter(is_active=True).exists()
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/gym/member_enroll.html", {
        "form": form, "no_plans": no_plans, "no_customers": no_customers,
    })


@login_required
def member_renew(request, member_id):
    member = get_object_or_404(GymMember.objects.for_company(request.company), id=member_id)
    form = RenewMemberForm(request.POST or None, company=request.company, initial={"membership_plan": member.membership_plan_id, "start_date": max(tz.now().date(), member.membership_end)})
    if request.method == "POST" and form.is_valid():
        gym_services.renew_member(company=request.company, user=request.user, member=member,
            warehouse=_default_warehouse(request.company), **form.cleaned_data)
        messages.success(request, "Membership renewed and invoice created.")
        return redirect("webapp:member_list")
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": f"Renew — {member.customer.name}", "cancel_url": "webapp:member_list"})


@login_required
def member_status_toggle(request, member_id):
    member = get_object_or_404(GymMember.objects.for_company(request.company), id=member_id)
    if request.method == "POST":
        member.status = "active" if member.status == "frozen" else "frozen"
        member.save(update_fields=["status"])
        messages.success(request, "Membership status updated.")
    return redirect("webapp:member_list")


@login_required
def attendance_today(request):
    company = request.company
    today = tz.now().date()
    entries = (
        Attendance.objects.for_company(company)
        .select_related("member__customer")
        .filter(check_in__date=today)
        .order_by("-check_in")
        if company else []
    )
    active_members = GymMember.objects.for_company(company).filter(status="active").select_related("customer") if company else []
    return render(request, "webapp/gym/attendance.html", {"entries": entries, "active_members": active_members})


@login_required
def attendance_check_in(request, member_id):
    company = request.company
    member = get_object_or_404(GymMember.objects.for_company(company), id=member_id)
    open_entry = Attendance.objects.for_company(company).filter(member=member, check_out__isnull=True).first()
    if open_entry:
        messages.error(request, f"{member.customer.name} is already checked in.")
    else:
        Attendance.objects.create(company=company, member=member, check_in=tz.now())
        messages.success(request, f"{member.customer.name} checked in.")
    return redirect("webapp:attendance_today")


@login_required
def attendance_check_out(request, entry_id):
    company = request.company
    entry = get_object_or_404(Attendance.objects.for_company(company), id=entry_id)
    entry.check_out = tz.now()
    entry.save(update_fields=["check_out"])
    messages.success(request, "Checked out.")
    return redirect("webapp:attendance_today")


@login_required
def gym_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    members = GymMember.objects.for_company(company)
    context = {
        "active_count": members.filter(status="active").count(),
        "expired_count": members.filter(status="expired").count(),
        "frozen_count": members.filter(status="frozen").count(),
        "plan_breakdown": (
            members.values("membership_plan__name")
            .annotate(count=Count("id"))
            .order_by("-count")
        ),
    }
    return render(request, "webapp/gym/reports.html", context)


# ================= SPA =================

@login_required
def spa_service_list(request):
    company = request.company
    services = SpaService.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/spa/service_list.html", {"services": services})


@login_required
def spa_service_add(request):
    company = request.company
    if request.method == "POST":
        form = SpaServiceForm(request.POST)
        if form.is_valid():
            spa_services.create_spa_service(
                company=company,
                name=form.cleaned_data["name"],
                duration_minutes=form.cleaned_data["duration_minutes"],
                price=form.cleaned_data["price"],
            )
            messages.success(request, "Service added.")
            return redirect("webapp:spa_service_list")
    else:
        form = SpaServiceForm()
    return render(request, "webapp/spa/service_form.html", {"form": form})


@login_required
def spa_service_edit(request, service_id):
    company = request.company
    obj = get_object_or_404(SpaService.objects.for_company(company), id=service_id)
    if request.method == "POST":
        form = SpaServiceForm(request.POST)
        if form.is_valid():
            obj.name = form.cleaned_data["name"]
            obj.duration_minutes = form.cleaned_data["duration_minutes"]
            obj.price = form.cleaned_data["price"]
            obj.save()
            messages.success(request, "Service updated.")
            return redirect("webapp:spa_service_list")
    else:
        form = SpaServiceForm(initial={"name": obj.name, "duration_minutes": obj.duration_minutes, "price": obj.price})
    return render(request, "webapp/spa/service_form.html", {"form": form, "editing": True})


@login_required
def spa_service_delete(request, service_id):
    company = request.company
    obj = get_object_or_404(SpaService.objects.for_company(company), id=service_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Service deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this service has appointments linked to it.")
        return redirect("webapp:spa_service_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:spa_service_list", "delete_url": "webapp:spa_service_delete", "delete_id": service_id,
    })


@login_required
def staff_list(request):
    company = request.company
    staff = Employee.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/staff_list.html", {"staff": staff})


@login_required
def staff_add(request):
    company = request.company
    if request.method == "POST":
        form = EmployeeForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Staff member added.")
            return redirect("webapp:staff_list")
    else:
        form = EmployeeForm()
    return render(request, "webapp/staff_form.html", {"form": form})


@login_required
def staff_edit(request, staff_id):
    company = request.company
    obj = get_object_or_404(Employee.objects.for_company(company), id=staff_id)
    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Staff member updated.")
            return redirect("webapp:staff_list")
    else:
        form = EmployeeForm(instance=obj)
    return render(request, "webapp/staff_form.html", {"form": form, "editing": True})


@login_required
def staff_delete(request, staff_id):
    company = request.company
    obj = get_object_or_404(Employee.objects.for_company(company), id=staff_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Staff member deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this staff member has appointments or other records linked to them.")
        return redirect("webapp:staff_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:staff_list", "delete_url": "webapp:staff_delete", "delete_id": staff_id,
    })


@login_required
def appointment_list(request):
    company = request.company
    appts = (
        Appointment.objects.for_company(company).select_related("customer", "service", "therapist")
        .order_by("-scheduled_at")
        if company else []
    )
    return render(request, "webapp/spa/appointment_list.html", {"appointments": appts})


@login_required
def appointment_book(request):
    company = request.company
    if request.method == "POST":
        form = BookAppointmentForm(request.POST, company=company)
        if form.is_valid():
            try:
                spa_services.book_appointment(
                    company=company,
                    user=request.user,
                    customer=form.cleaned_data["customer"],
                    service=form.cleaned_data["service"],
                    therapist=form.cleaned_data["therapist"],
                    scheduled_at=form.cleaned_data["scheduled_at"],
                    warehouse=_default_warehouse(company),
                    commission_rate_percent=form.cleaned_data["commission_rate_percent"] or 0,
                )
                messages.success(request, "Appointment booked and invoiced.")
                return redirect("webapp:appointment_list")
            except Exception as exc:
                messages.error(request, f"Couldn't book appointment: {exc}")
    else:
        form = BookAppointmentForm(company=company)

    no_services = not SpaService.objects.for_company(company).filter(is_active=True).exists()
    no_staff = not Employee.objects.for_company(company).filter(is_active=True).exists()
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/spa/appointment_book.html", {
        "form": form, "no_services": no_services, "no_staff": no_staff, "no_customers": no_customers,
    })


@login_required
def appointment_complete(request, appointment_id):
    company = request.company
    appt = get_object_or_404(Appointment.objects.for_company(company), id=appointment_id)
    spa_services.complete_appointment(appt)
    messages.success(request, "Appointment marked completed.")
    return redirect("webapp:appointment_list")


@login_required
def appointment_cancel(request, appointment_id):
    company = request.company
    appt = get_object_or_404(Appointment.objects.for_company(company), id=appointment_id)
    spa_services.cancel_appointment(appt)
    messages.success(request, "Appointment cancelled.")
    return redirect("webapp:appointment_list")


@login_required
def spa_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    appts = Appointment.objects.for_company(company)
    completed = appts.filter(status="completed")
    context = {
        "booked_count": appts.filter(status="booked").count(),
        "completed_count": completed.count(),
        "cancelled_count": appts.filter(status__in=["cancelled", "no_show"]).count(),
        "revenue": completed.aggregate(total=Sum("price"))["total"] or 0,
        "by_service": (
            completed.values("service__name").annotate(count=Count("id"), revenue=Sum("price")).order_by("-revenue")
        ),
    }
    return render(request, "webapp/spa/reports.html", context)


# ================= PLATFORM ADMIN: REGISTER NEW CLIENT =================

@login_required
def register_client(request):
    """Platform-owner provisioning wizard.

    Creates the tenant, assigns one or many business suites, and applies the
    exact module catalogue selected by the platform owner in a single step.
    """
    if not request.user.is_platform_admin:
        messages.error(request, "Only a platform admin can add new clients.")
        return redirect("webapp:dashboard")

    # Keep the friendly UI capabilities in the same canonical module catalogue
    # used by the post-creation Modules screen.
    for code, name in WEB_FEATURES:
        Module.objects.get_or_create(code=code, defaults={"name": name, "is_core": False})

    # Make every catalogue business visible even on installations upgraded from
    # an older database. seed_platform will add richer default mappings, but the
    # provisioning screen itself must never silently hide a sellable business.
    for code, name in BUSINESS_TYPE_CHOICES:
        BusinessType.objects.get_or_create(code=code, defaults={"name": name})

    if request.method == "POST":
        form = RegisterClientForm(request.POST)
        if form.is_valid():
            from django.utils.text import slugify
            from apps.tenants.services import create_company_with_owner

            User = get_user_model()
            business_name = form.cleaned_data["business_name"]
            primary_code = form.cleaned_data["business_type"]
            primary_name = BUSINESS_TYPE_MAP.get(primary_code, primary_code.replace("_", " ").title())
            selected_suite_codes = set(request.POST.getlist("business_suites"))
            selected_suite_codes.add(primary_code)
            valid_codes = set(BUSINESS_TYPE_MAP)
            selected_suite_codes &= valid_codes

            enabled_ids = {int(x) for x in request.POST.getlist("modules") if x.isdigit()}
            custom_module_lines = [x.strip() for x in request.POST.get("custom_modules", "").splitlines() if x.strip()]

            base_slug = slugify(business_name)
            slug = base_slug
            n = 1
            while Company.objects.filter(slug=slug).exists():
                n += 1
                slug = f"{base_slug}-{n}"

            try:
                with transaction.atomic():
                    owner = User.objects.create_user(
                        username=form.cleaned_data["owner_username"],
                        email=form.cleaned_data["owner_email"],
                        password=form.cleaned_data["owner_password"],
                    )
                    primary_bt, _ = BusinessType.objects.get_or_create(
                        code=primary_code, defaults={"name": primary_name}
                    )
                    company = create_company_with_owner(
                        user=owner, name=business_name, slug=slug, business_type=primary_bt,
                        country=form.cleaned_data["country"], plan=form.cleaned_data["plan"],
                    )

                    # Multi-business tenant: one legal company/accounting ledger,
                    # multiple operational suites.
                    for code in selected_suite_codes:
                        bt = BusinessType.objects.get(code=code)
                        CompanyBusinessType.objects.update_or_create(
                            company=company, business_type=bt,
                            defaults={"is_active": True, "is_primary": code == primary_code},
                        )

                    # Create one-off capabilities entered as "Name | code" (code optional).
                    from django.utils.text import slugify as module_slugify
                    for line in custom_module_lines:
                        if "|" in line:
                            custom_name, custom_code = [part.strip() for part in line.split("|", 1)]
                        else:
                            custom_name, custom_code = line, module_slugify(line).replace("-", "_")
                        if custom_name and custom_code:
                            module, _ = Module.objects.get_or_create(
                                code=custom_code, defaults={"name": custom_name, "is_core": False}
                            )
                            enabled_ids.add(module.id)

                    # Exact commercial entitlement chosen by platform owner.
                    # Core modules can never be disabled.
                    for module in Module.objects.all():
                        is_on = module.is_core or module.id in enabled_ids
                        CompanyModule.objects.update_or_create(
                            company=company, module=module, defaults={"is_active": is_on}
                        )

                messages.success(
                    request,
                    f"Client created: {company.name} · {len(selected_suite_codes)} business suite(s) provisioned. Login username: {owner.username}",
                )
                return redirect("webapp:platform_admin_company_detail", company_id=company.id)
            except Exception as exc:
                messages.error(request, f"Couldn't create client: {exc}")
    else:
        form = RegisterClientForm()

    modules = list(Module.objects.all().order_by("is_core", "name"))
    module_rows = [(m, m.is_core) for m in modules]
    default_map = {}
    for bt in BusinessType.objects.prefetch_related("default_modules__module"):
        default_map[bt.code] = [row.module_id for row in bt.default_modules.all()]

    business_groups = {}
    for code, name in BUSINESS_TYPE_CHOICES:
        business_groups.setdefault(business_group(code), []).append((code, name))

    return render(request, "webapp/register_client.html", {
        "form": form,
        "module_rows": module_rows,
        "business_groups": business_groups,
        "default_module_map": default_map,
        "web_feature_ids": [m.id for m in modules if m.code.startswith("webui_")],
    })


# ================= TEXTILE =================

@login_required
def fabric_list(request):
    company = request.company
    fabrics = (
        FabricDetail.objects.for_company(company).select_related("product", "product__category")
        .order_by("product__name")
        if company else []
    )
    return render(request, "webapp/textile/fabric_list.html", {"fabrics": fabrics})


@login_required
def fabric_add(request):
    company = request.company
    if request.method == "POST":
        form = FabricForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            product = Product.objects.create(
                company=company, sku=d["sku"], name=d["name"], category=d["category"], unit=d["unit"],
                cost_price=d["cost_price"], selling_price=d["selling_price"],
            )
            FabricDetail.objects.create(
                company=company, product=product, fabric_type=d["fabric_type"], color=d["color"],
                design=d["design"], material=d["material"], length_per_unit=d["length_per_unit"],
                width_inches=d["width_inches"],
            )
            messages.success(request, "Fabric added.")
            return redirect("webapp:fabric_list")
    else:
        form = FabricForm(company=company)
    return render(request, "webapp/textile/fabric_form.html", {"form": form})


@login_required
def fabric_edit(request, fabric_id):
    company = request.company
    detail = get_object_or_404(FabricDetail.objects.for_company(company).select_related("product"), id=fabric_id)
    product = detail.product
    if request.method == "POST":
        form = FabricForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            product.sku = d["sku"]; product.name = d["name"]; product.category = d["category"]
            product.unit = d["unit"]; product.cost_price = d["cost_price"]; product.selling_price = d["selling_price"]
            product.save()
            detail.fabric_type = d["fabric_type"]; detail.color = d["color"]; detail.design = d["design"]
            detail.material = d["material"]; detail.length_per_unit = d["length_per_unit"]
            detail.width_inches = d["width_inches"]
            detail.save()
            messages.success(request, "Fabric updated.")
            return redirect("webapp:fabric_list")
    else:
        form = FabricForm(company=company, initial={
            "sku": product.sku, "name": product.name, "category": product.category_id, "unit": product.unit_id,
            "cost_price": product.cost_price, "selling_price": product.selling_price,
            "fabric_type": detail.fabric_type, "color": detail.color, "design": detail.design,
            "material": detail.material, "length_per_unit": detail.length_per_unit, "width_inches": detail.width_inches,
        })
    return render(request, "webapp/textile/fabric_form.html", {"form": form, "editing": True})


@login_required
def fabric_delete(request, fabric_id):
    company = request.company
    detail = get_object_or_404(FabricDetail.objects.for_company(company).select_related("product"), id=fabric_id)
    product = detail.product
    if request.method == "POST":
        try:
            product.delete()
            messages.success(request, "Fabric deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this fabric has orders or sales linked to it.")
        return redirect("webapp:fabric_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": product, "cancel_url": "webapp:fabric_list", "delete_url": "webapp:fabric_delete", "delete_id": fabric_id,
    })


@login_required
def measurement_list(request):
    company = request.company
    measurements = (
        Measurement.objects.for_company(company).select_related("customer").order_by("-taken_on")
        if company else []
    )
    return render(request, "webapp/textile/measurement_list.html", {"measurements": measurements})


@login_required
def measurement_add(request):
    company = request.company
    if request.method == "POST":
        form = MeasurementForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            values = {k: str(d[k]) for k in ("chest", "waist", "sleeve", "length") if d.get(k) is not None}
            Measurement.objects.create(
                company=company, customer=d["customer"], garment_type=d["garment_type"],
                values=values, taken_on=d["taken_on"], notes=d["notes"],
            )
            messages.success(request, "Measurement saved.")
            return redirect("webapp:measurement_list")
    else:
        form = MeasurementForm(company=company, initial={"taken_on": tz.now().date()})

    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/textile/measurement_form.html", {"form": form, "no_customers": no_customers})


@login_required
def measurement_edit(request, measurement_id):
    company = request.company
    measurement = get_object_or_404(Measurement.objects.for_company(company), id=measurement_id)
    if request.method == "POST":
        form = MeasurementForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            values = {k: str(d[k]) for k in ("chest", "waist", "sleeve", "length") if d.get(k) is not None}
            measurement.customer = d["customer"]; measurement.garment_type = d["garment_type"]
            measurement.values = values; measurement.taken_on = d["taken_on"]; measurement.notes = d["notes"]
            measurement.save()
            messages.success(request, "Measurement updated.")
            return redirect("webapp:measurement_list")
    else:
        existing = {f"{k}": measurement.values.get(k) for k in ("chest", "waist", "sleeve", "length")}
        form = MeasurementForm(company=company, initial={
            "customer": measurement.customer_id, "garment_type": measurement.garment_type,
            "taken_on": measurement.taken_on, "notes": measurement.notes, **existing,
        })
    return render(request, "webapp/textile/measurement_form.html", {"form": form, "editing": True})


@login_required
def measurement_delete(request, measurement_id):
    company = request.company
    measurement = get_object_or_404(Measurement.objects.for_company(company), id=measurement_id)
    if request.method == "POST":
        try:
            measurement.delete()
            messages.success(request, "Measurement deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this measurement is linked to an order.")
        return redirect("webapp:measurement_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": measurement, "cancel_url": "webapp:measurement_list",
        "delete_url": "webapp:measurement_delete", "delete_id": measurement_id,
    })


@login_required
def order_list(request):
    company = request.company
    orders = (
        TailoringOrder.objects.for_company(company).select_related("customer").order_by("-order_date")
        if company else []
    )
    return render(request, "webapp/textile/order_list.html", {"orders": orders})


@login_required
def order_add(request):
    company = request.company
    if request.method == "POST":
        form = TailoringOrderForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            textile_services.create_tailoring_order(
                company=company, user=request.user, customer=d["customer"], order_date=d["order_date"],
                expected_delivery_date=d["expected_delivery_date"], price=d["price"],
                warehouse=_default_warehouse(company),
                measurement=d["measurement"], fabric_product=d["fabric_product"], notes=d["notes"],
            )
            messages.success(request, "Order created.")
            return redirect("webapp:order_list")
    else:
        form = TailoringOrderForm(company=company, initial={"order_date": tz.now().date()})

    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/textile/order_form.html", {"form": form, "no_customers": no_customers})


@login_required
def order_edit(request, order_id):
    company = request.company
    order = get_object_or_404(TailoringOrder.objects.for_company(company), id=order_id)
    if request.method == "POST":
        form = TailoringOrderForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            order.customer = d["customer"]; order.measurement = d["measurement"]; order.fabric_product = d["fabric_product"]
            order.order_date = d["order_date"]; order.expected_delivery_date = d["expected_delivery_date"]
            order.price = d["price"]; order.notes = d["notes"]
            order.save()
            messages.success(request, "Order updated.")
            return redirect("webapp:order_list")
    else:
        form = TailoringOrderForm(company=company, initial={
            "customer": order.customer_id, "measurement": order.measurement_id, "fabric_product": order.fabric_product_id,
            "order_date": order.order_date, "expected_delivery_date": order.expected_delivery_date,
            "price": order.price, "notes": order.notes,
        })
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/textile/order_form.html", {"form": form, "no_customers": no_customers, "editing": True})


@login_required
def order_cancel(request, order_id):
    company = request.company
    order = get_object_or_404(TailoringOrder.objects.for_company(company), id=order_id)
    if request.method == "POST":
        order.status = "cancelled"
        order.save(update_fields=["status"])
        messages.success(request, "Order cancelled.")
        return redirect("webapp:order_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": order, "cancel_url": "webapp:order_list", "delete_url": "webapp:order_cancel", "delete_id": order_id,
    })


@login_required
def order_mark_ready(request, order_id):
    company = request.company
    order = get_object_or_404(TailoringOrder.objects.for_company(company), id=order_id)
    textile_services.mark_ready(order)
    messages.success(request, "Order marked ready for pickup.")
    return redirect("webapp:order_list")


@login_required
def order_mark_delivered(request, order_id):
    company = request.company
    order = get_object_or_404(TailoringOrder.objects.for_company(company), id=order_id)
    textile_services.mark_delivered(order, tz.now().date())
    messages.success(request, "Order marked delivered.")
    return redirect("webapp:order_list")


@login_required
def textile_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    orders = TailoringOrder.objects.for_company(company)
    delivered = orders.filter(status="delivered")
    context = {
        "pending_count": orders.filter(status="pending").count(),
        "in_progress_count": orders.filter(status="in_progress").count(),
        "ready_count": orders.filter(status="ready").count(),
        "delivered_count": delivered.count(),
        "revenue": delivered.aggregate(total=Sum("price"))["total"] or 0,
    }
    return render(request, "webapp/textile/reports.html", context)


# ================= VEHICLE WASH =================

@login_required
def vehicle_list(request):
    company = request.company
    vehicles = Vehicle.objects.for_company(company).select_related("customer").order_by("vehicle_number") if company else []
    return render(request, "webapp/vehicle_wash/vehicle_list.html", {"vehicles": vehicles})


@login_required
def vehicle_add(request):
    company = request.company
    if request.method == "POST":
        form = VehicleForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Vehicle added.")
            return redirect("webapp:vehicle_list")
    else:
        form = VehicleForm(company=company)
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/vehicle_wash/vehicle_form.html", {"form": form, "no_customers": no_customers})


@login_required
def vehicle_edit(request, vehicle_id):
    company = request.company
    obj = get_object_or_404(Vehicle.objects.for_company(company), id=vehicle_id)
    if request.method == "POST":
        form = VehicleForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Vehicle updated.")
            return redirect("webapp:vehicle_list")
    else:
        form = VehicleForm(instance=obj, company=company)
    return render(request, "webapp/vehicle_wash/vehicle_form.html", {"form": form, "editing": True})


@login_required
def vehicle_delete(request, vehicle_id):
    company = request.company
    obj = get_object_or_404(Vehicle.objects.for_company(company), id=vehicle_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Vehicle deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this vehicle has wash orders linked to it.")
        return redirect("webapp:vehicle_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:vehicle_list", "delete_url": "webapp:vehicle_delete", "delete_id": vehicle_id,
    })


@login_required
def wash_package_list(request):
    company = request.company
    packages = WashPackage.objects.for_company(company).order_by("vehicle_type", "price") if company else []
    return render(request, "webapp/vehicle_wash/package_list.html", {"packages": packages})


@login_required
def wash_package_add(request):
    company = request.company
    if request.method == "POST":
        form = WashPackageForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            wash_services.create_wash_package(
                company=company, name=d["name"], vehicle_type=d["vehicle_type"], price=d["price"],
                duration_minutes=d["duration_minutes"], description=d["description"],
            )
            messages.success(request, "Wash package added.")
            return redirect("webapp:wash_package_list")
    else:
        form = WashPackageForm()
    return render(request, "webapp/vehicle_wash/package_form.html", {"form": form})


@login_required
def wash_package_edit(request, package_id):
    company = request.company
    obj = get_object_or_404(WashPackage.objects.for_company(company), id=package_id)
    if request.method == "POST":
        form = WashPackageForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Wash package updated.")
            return redirect("webapp:wash_package_list")
    else:
        form = WashPackageForm(instance=obj)
    return render(request, "webapp/vehicle_wash/package_form.html", {"form": form, "editing": True})


@login_required
def wash_package_delete(request, package_id):
    company = request.company
    obj = get_object_or_404(WashPackage.objects.for_company(company), id=package_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Wash package deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this package has orders linked to it.")
        return redirect("webapp:wash_package_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:wash_package_list", "delete_url": "webapp:wash_package_delete", "delete_id": package_id,
    })


@login_required
def wash_order_list(request):
    company = request.company
    orders = (
        WashOrder.objects.for_company(company).select_related("vehicle", "package", "staff")
        .order_by("-scheduled_at")
        if company else []
    )
    return render(request, "webapp/vehicle_wash/order_list.html", {"orders": orders})


@login_required
def wash_order_book(request):
    company = request.company
    if request.method == "POST":
        form = BookWashForm(request.POST, company=company)
        if form.is_valid():
            wash_services.book_wash(
                company=company,
                vehicle=form.cleaned_data["vehicle"],
                package=form.cleaned_data["package"],
                staff=form.cleaned_data["staff"],
                scheduled_at=form.cleaned_data["scheduled_at"],
                price=form.cleaned_data["price"],
            )
            messages.success(request, "Wash booked.")
            return redirect("webapp:wash_order_list")
    else:
        form = BookWashForm(company=company, initial={"scheduled_at": tz.now()})

    no_vehicles = not Vehicle.objects.for_company(company).exists()
    no_packages = not WashPackage.objects.for_company(company).filter(is_active=True).exists()
    return render(request, "webapp/vehicle_wash/order_book.html", {
        "form": form, "no_vehicles": no_vehicles, "no_packages": no_packages,
    })


@login_required
def wash_order_start(request, order_id):
    company = request.company
    order = get_object_or_404(WashOrder.objects.for_company(company), id=order_id)
    try:
        wash_services.start_wash(order)
        messages.success(request, "Wash started.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("webapp:wash_order_list")


@login_required
def wash_order_complete(request, order_id):
    company = request.company
    order = get_object_or_404(WashOrder.objects.for_company(company), id=order_id)
    try:
        wash_services.complete_wash(order, user=request.user, warehouse=_default_warehouse(company))
        messages.success(request, "Wash completed.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("webapp:wash_order_list")


@login_required
def wash_order_cancel(request, order_id):
    company = request.company
    order = get_object_or_404(WashOrder.objects.for_company(company), id=order_id)
    try:
        wash_services.cancel_wash(order)
        messages.success(request, "Wash cancelled.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("webapp:wash_order_list")


@login_required
def vehicle_wash_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    orders = WashOrder.objects.for_company(company)
    completed = orders.filter(status="completed")
    context = {
        "booked_count": orders.filter(status="booked").count(),
        "in_progress_count": orders.filter(status="in_progress").count(),
        "completed_count": completed.count(),
        "cancelled_count": orders.filter(status="cancelled").count(),
        "revenue": completed.aggregate(total=Sum("price"))["total"] or 0,
        "by_package": (
            completed.values("package__name").annotate(count=Count("id"), revenue=Sum("price")).order_by("-revenue")
        ),
    }
    return render(request, "webapp/vehicle_wash/reports.html", context)


# ================= SPORTS SHOP =================

@login_required
def sports_product_list(request):
    company = request.company
    details = (
        SportsProductDetail.objects.for_company(company).select_related("product", "product__category")
        .order_by("product__name")
        if company else []
    )
    return render(request, "webapp/sports_shop/product_list.html", {"details": details})


@login_required
def sports_product_add(request):
    company = request.company
    if request.method == "POST":
        form = SportsProductForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            product = Product.objects.create(
                company=company, sku=d["sku"], name=d["name"], category=d["category"], unit=d["unit"],
                cost_price=d["cost_price"], selling_price=d["selling_price"],
            )
            SportsProductDetail.objects.create(
                company=company, product=product, sport_category=d["sport_category"],
                size=d["size"], gender=d["gender"], material=d["material"],
            )
            messages.success(request, "Product added.")
            return redirect("webapp:sports_product_list")
    else:
        form = SportsProductForm(company=company)
    return render(request, "webapp/sports_shop/product_form.html", {"form": form})


# ================= CYCLE SHOP =================

@login_required
def cycle_unit_list(request):
    company = request.company
    units = CycleUnit.objects.for_company(company).select_related("product").order_by("-id") if company else []
    return render(request, "webapp/cycle_shop/unit_list.html", {"units": units})


@login_required
def cycle_unit_add(request):
    company = request.company
    if request.method == "POST":
        form = CycleUnitForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Cycle unit added.")
            return redirect("webapp:cycle_unit_list")
    else:
        form = CycleUnitForm(company=company)
    return render(request, "webapp/cycle_shop/unit_form.html", {"form": form})


@login_required
def cycle_unit_edit(request, unit_id):
    company = request.company
    obj = get_object_or_404(CycleUnit.objects.for_company(company), id=unit_id)
    if request.method == "POST":
        form = CycleUnitForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Cycle unit updated.")
            return redirect("webapp:cycle_unit_list")
    else:
        form = CycleUnitForm(instance=obj, company=company)
    return render(request, "webapp/cycle_shop/unit_form.html", {"form": form, "editing": True})


@login_required
def cycle_unit_delete(request, unit_id):
    company = request.company
    obj = get_object_or_404(CycleUnit.objects.for_company(company), id=unit_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Cycle unit deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this unit has service tickets linked to it.")
        return redirect("webapp:cycle_unit_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:cycle_unit_list", "delete_url": "webapp:cycle_unit_delete", "delete_id": unit_id,
    })


@login_required
def cycle_sell(request, unit_id):
    company = request.company
    unit = get_object_or_404(CycleUnit.objects.for_company(company), id=unit_id)
    if unit.status != "in_stock":
        messages.error(request, "This unit isn't available to sell.")
        return redirect("webapp:cycle_unit_list")

    if request.method == "POST":
        form = SellCycleForm(request.POST, company=company)
        if form.is_valid():
            cycle_services.sell_unit(
                unit, buyer=form.cleaned_data["buyer"], sold_price=form.cleaned_data["sold_price"],
                sold_date=form.cleaned_data["sold_date"],
            )
            messages.success(request, f"Sold {unit.product.name} (#{unit.serial_number}).")
            return redirect("webapp:cycle_unit_list")
    else:
        form = SellCycleForm(initial={"sold_date": tz.now().date()}, company=company)
    return render(request, "webapp/cycle_shop/sell_form.html", {"form": form, "unit": unit})


@login_required
def service_ticket_list(request):
    company = request.company
    tickets = (
        ServiceTicket.objects.for_company(company).select_related("customer", "cycle_unit").order_by("-received_date")
        if company else []
    )
    return render(request, "webapp/cycle_shop/ticket_list.html", {"tickets": tickets})


@login_required
def service_ticket_add(request):
    company = request.company
    if request.method == "POST":
        form = ServiceTicketForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            ServiceTicket.objects.create(
                company=company, customer=d["customer"], cycle_unit=d["cycle_unit"],
                cycle_description=d["cycle_description"], issue_description=d["issue_description"],
                staff=d["staff"], received_date=d["received_date"], status="received",
            )
            messages.success(request, "Service ticket created.")
            return redirect("webapp:service_ticket_list")
    else:
        form = ServiceTicketForm(company=company, initial={"received_date": tz.now().date()})
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/cycle_shop/ticket_form.html", {"form": form, "no_customers": no_customers})


@login_required
def service_ticket_start(request, ticket_id):
    company = request.company
    ticket = get_object_or_404(ServiceTicket.objects.for_company(company), id=ticket_id)
    try:
        cycle_services.start_service(ticket)
        messages.success(request, "Ticket started.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("webapp:service_ticket_list")


@login_required
def service_ticket_complete(request, ticket_id):
    company = request.company
    ticket = get_object_or_404(ServiceTicket.objects.for_company(company), id=ticket_id)
    cost = request.GET.get("cost") or request.POST.get("cost") or "0"
    try:
        cycle_services.complete_service(ticket, cost=cost)
        messages.success(request, "Ticket marked completed.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("webapp:service_ticket_list")


@login_required
def service_ticket_deliver(request, ticket_id):
    company = request.company
    ticket = get_object_or_404(ServiceTicket.objects.for_company(company), id=ticket_id)
    try:
        cycle_services.deliver_service(ticket, delivered_date=tz.now().date())
        messages.success(request, "Ticket delivered.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("webapp:service_ticket_list")


@login_required
def cycle_shop_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    units = CycleUnit.objects.for_company(company)
    sold = units.filter(status="sold")
    context = {
        "in_stock_count": units.filter(status="in_stock").count(),
        "sold_count": sold.count(),
        "revenue": sold.aggregate(total=Sum("sold_price"))["total"] or 0,
        "open_tickets": ServiceTicket.objects.for_company(company).exclude(status="delivered").count(),
    }
    return render(request, "webapp/cycle_shop/reports.html", context)


# ================= SALOON =================

@login_required
def saloon_service_list(request):
    company = request.company
    services = SaloonService.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/saloon/service_list.html", {"services": services})


@login_required
def saloon_service_add(request):
    company = request.company
    if request.method == "POST":
        form = SaloonServiceForm(request.POST)
        if form.is_valid():
            saloon_services.create_saloon_service(
                company=company, name=form.cleaned_data["name"],
                duration_minutes=form.cleaned_data["duration_minutes"], price=form.cleaned_data["price"],
            )
            messages.success(request, "Service added.")
            return redirect("webapp:saloon_service_list")
    else:
        form = SaloonServiceForm()
    return render(request, "webapp/saloon/service_form.html", {"form": form})


@login_required
def saloon_service_edit(request, service_id):
    company = request.company
    obj = get_object_or_404(SaloonService.objects.for_company(company), id=service_id)
    if request.method == "POST":
        form = SaloonServiceForm(request.POST)
        if form.is_valid():
            obj.name = form.cleaned_data["name"]
            obj.duration_minutes = form.cleaned_data["duration_minutes"]
            obj.price = form.cleaned_data["price"]
            obj.save()
            messages.success(request, "Service updated.")
            return redirect("webapp:saloon_service_list")
    else:
        form = SaloonServiceForm(initial={"name": obj.name, "duration_minutes": obj.duration_minutes, "price": obj.price})
    return render(request, "webapp/saloon/service_form.html", {"form": form, "editing": True})


@login_required
def saloon_service_delete(request, service_id):
    company = request.company
    obj = get_object_or_404(SaloonService.objects.for_company(company), id=service_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Service deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this service has appointments linked to it.")
        return redirect("webapp:saloon_service_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:saloon_service_list", "delete_url": "webapp:saloon_service_delete", "delete_id": service_id,
    })


@login_required
def saloon_appointment_list(request):
    company = request.company
    appts = (
        SaloonAppointment.objects.for_company(company).select_related("customer", "service", "stylist")
        .order_by("-scheduled_at")
        if company else []
    )
    return render(request, "webapp/saloon/appointment_list.html", {"appointments": appts})


@login_required
def saloon_appointment_book(request):
    company = request.company
    if request.method == "POST":
        form = BookSaloonAppointmentForm(request.POST, company=company)
        if form.is_valid():
            try:
                saloon_services.book_appointment(
                    company=company, user=request.user, customer=form.cleaned_data["customer"], service=form.cleaned_data["service"],
                    stylist=form.cleaned_data["stylist"], scheduled_at=form.cleaned_data["scheduled_at"],
                    warehouse=_default_warehouse(company),
                    commission_rate_percent=form.cleaned_data["commission_rate_percent"] or 0,
                )
                messages.success(request, "Appointment booked.")
                return redirect("webapp:saloon_appointment_list")
            except Exception as exc:
                messages.error(request, f"Couldn't book: {exc}")
    else:
        form = BookSaloonAppointmentForm(company=company)
    no_services = not SaloonService.objects.for_company(company).filter(is_active=True).exists()
    no_staff = not Employee.objects.for_company(company).filter(is_active=True).exists()
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/saloon/appointment_book.html", {
        "form": form, "no_services": no_services, "no_staff": no_staff, "no_customers": no_customers,
    })


@login_required
def saloon_appointment_complete(request, appointment_id):
    company = request.company
    appt = get_object_or_404(SaloonAppointment.objects.for_company(company), id=appointment_id)
    saloon_services.complete_appointment(appt)
    messages.success(request, "Marked completed.")
    return redirect("webapp:saloon_appointment_list")


@login_required
def saloon_appointment_cancel(request, appointment_id):
    company = request.company
    appt = get_object_or_404(SaloonAppointment.objects.for_company(company), id=appointment_id)
    saloon_services.cancel_appointment(appt)
    messages.success(request, "Cancelled.")
    return redirect("webapp:saloon_appointment_list")


@login_required
def saloon_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    appts = SaloonAppointment.objects.for_company(company)
    completed = appts.filter(status="completed")
    context = {
        "booked_count": appts.filter(status="booked").count(),
        "completed_count": completed.count(),
        "revenue": completed.aggregate(total=Sum("price"))["total"] or 0,
        "by_service": completed.values("service__name").annotate(count=Count("id"), revenue=Sum("price")).order_by("-revenue"),
    }
    return render(request, "webapp/saloon/reports.html", context)


# Generic case-record workflow used by clinics, education, repair and field-service clients.
@login_required
@require_business_group("service", "saloon")
def service_profile_list(request):
    profiles = ServiceClientProfile.objects.for_company(request.company).select_related("customer").order_by("subject_name")
    return render(request, "webapp/service_suite/profile_list.html", {"profiles": profiles})


@login_required
@require_business_group("service", "saloon")
def service_profile_form(request, profile_id=None):
    company = request.company
    profile = get_object_or_404(ServiceClientProfile.objects.for_company(company), id=profile_id) if profile_id else None
    form = ServiceClientProfileForm(request.POST or None, instance=profile, company=company)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = company; obj.save()
        messages.success(request, "Client record saved.")
        return redirect("webapp:service_profile_list")
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Client / subject record", "cancel_url": "webapp:service_profile_list"})


@login_required
@require_business_group("service", "saloon")
def service_case_list(request):
    cases = ServiceCase.objects.for_company(request.company).select_related("profile", "profile__customer", "assigned_staff").order_by("-opened_date")
    return render(request, "webapp/service_suite/case_list.html", {"cases": cases})


@login_required
@require_business_group("service", "saloon")
def service_case_form(request, case_id=None):
    company = request.company
    case = get_object_or_404(ServiceCase.objects.for_company(company), id=case_id) if case_id else None
    form = ServiceCaseForm(request.POST or None, instance=case, company=company, initial={"opened_date": tz.now().date()})
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = company
        if obj.status == "completed" and not obj.closed_date: obj.closed_date = tz.now().date()
        obj.save(); messages.success(request, "Case / work order saved.")
        return redirect("webapp:service_case_detail", case_id=obj.id)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Case / work order", "cancel_url": "webapp:service_case_list"})


@login_required
@require_business_group("service", "saloon")
def service_case_detail(request, case_id):
    case = get_object_or_404(ServiceCase.objects.for_company(request.company).select_related("profile", "assigned_staff"), id=case_id)
    return render(request, "webapp/service_suite/case_detail.html", {"case": case, "notes": case.case_notes.order_by("-date", "-id")})


@login_required
@require_business_group("service", "saloon")
def service_case_note_add(request, case_id):
    case = get_object_or_404(ServiceCase.objects.for_company(request.company), id=case_id)
    form = ServiceCaseNoteForm(request.POST or None, initial={"date": tz.now().date()})
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.case = case; obj.created_by = request.user; obj.save()
        messages.success(request, "Case note added.")
        return redirect("webapp:service_case_detail", case_id=case.id)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Add case/session note", "cancel_url": "webapp:service_case_detail", "cancel_id": case.id})


@login_required
@require_business_group("service", "saloon")
def service_package_list(request):
    packages = SaloonServicePackage.objects.for_company(request.company).select_related("service").order_by("name")
    customer_packages = SaloonCustomerPackage.objects.for_company(request.company).select_related("customer", "package").order_by("-purchased_on")
    return render(request, "webapp/service_suite/package_list.html", {"packages": packages, "customer_packages": customer_packages})


@login_required
@require_business_group("service", "saloon")
def service_package_add(request):
    form = SaloonServicePackageForm(request.POST or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        saloon_services.create_service_package(company=request.company, **form.cleaned_data)
        messages.success(request, "Service package created.")
        return redirect("webapp:service_package_list")
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Service package", "cancel_url": "webapp:service_package_list"})


@login_required
@require_business_group("service", "saloon")
def service_package_purchase(request):
    form = SaloonPackagePurchaseForm(request.POST or None, company=request.company, initial={"purchased_on": tz.now().date()})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        saloon_services.purchase_package(company=request.company, user=request.user, customer=d["customer"],
            package=d["package"], purchased_on=d["purchased_on"], warehouse=d["warehouse"])
        messages.success(request, "Package sold and invoice created.")
        return redirect("webapp:service_package_list")
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": "Sell service package", "cancel_url": "webapp:service_package_list"})


@login_required
@require_business_group("service", "saloon")
def service_suite_reports(request):
    company = request.company
    today = tz.now().date()
    cases = ServiceCase.objects.for_company(company)
    notes = ServiceCaseNote.objects.for_company(company)
    appointments = SaloonAppointment.objects.for_company(company)
    context = {
        "open_cases": cases.exclude(status__in=["completed", "cancelled"]).count(),
        "completed_cases": cases.filter(status="completed").count(),
        "due_cases": cases.exclude(status__in=["completed", "cancelled"]).filter(due_date__lte=today).count(),
        "follow_ups": notes.filter(next_follow_up__gte=today).order_by("next_follow_up")[:20],
        "appointment_revenue": appointments.filter(status="completed").aggregate(t=Sum("price"))["t"] or 0,
        "today_appointments": appointments.filter(scheduled_at__date=today).count(),
    }
    return render(request, "webapp/service_suite/reports.html", context)


# ================= BEAUTY PARLOUR =================

@login_required
def beauty_service_list(request):
    company = request.company
    services = BeautyService.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/beauty_parlour/service_list.html", {"services": services})


@login_required
def beauty_service_add(request):
    company = request.company
    if request.method == "POST":
        form = BeautyServiceForm(request.POST)
        if form.is_valid():
            beauty_services.create_beauty_service(
                company=company, name=form.cleaned_data["name"],
                duration_minutes=form.cleaned_data["duration_minutes"], price=form.cleaned_data["price"],
            )
            messages.success(request, "Service added.")
            return redirect("webapp:beauty_service_list")
    else:
        form = BeautyServiceForm()
    return render(request, "webapp/beauty_parlour/service_form.html", {"form": form})


@login_required
def beauty_service_edit(request, service_id):
    company = request.company
    obj = get_object_or_404(BeautyService.objects.for_company(company), id=service_id)
    if request.method == "POST":
        form = BeautyServiceForm(request.POST)
        if form.is_valid():
            obj.name = form.cleaned_data["name"]
            obj.duration_minutes = form.cleaned_data["duration_minutes"]
            obj.price = form.cleaned_data["price"]
            obj.save()
            messages.success(request, "Service updated.")
            return redirect("webapp:beauty_service_list")
    else:
        form = BeautyServiceForm(initial={"name": obj.name, "duration_minutes": obj.duration_minutes, "price": obj.price})
    return render(request, "webapp/beauty_parlour/service_form.html", {"form": form, "editing": True})


@login_required
def beauty_service_delete(request, service_id):
    company = request.company
    obj = get_object_or_404(BeautyService.objects.for_company(company), id=service_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Service deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this service has appointments linked to it.")
        return redirect("webapp:beauty_service_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:beauty_service_list", "delete_url": "webapp:beauty_service_delete", "delete_id": service_id,
    })


@login_required
def beauty_appointment_list(request):
    company = request.company
    appts = (
        BeautyAppointment.objects.for_company(company).select_related("customer", "service", "beautician")
        .order_by("-scheduled_at")
        if company else []
    )
    return render(request, "webapp/beauty_parlour/appointment_list.html", {"appointments": appts})


@login_required
def beauty_appointment_book(request):
    company = request.company
    if request.method == "POST":
        form = BookBeautyAppointmentForm(request.POST, company=company)
        if form.is_valid():
            try:
                beauty_services.book_appointment(
                    company=company, user=request.user, customer=form.cleaned_data["customer"], service=form.cleaned_data["service"],
                    beautician=form.cleaned_data["beautician"], scheduled_at=form.cleaned_data["scheduled_at"],
                    warehouse=_default_warehouse(company),
                    commission_rate_percent=form.cleaned_data["commission_rate_percent"] or 0,
                )
                messages.success(request, "Appointment booked.")
                return redirect("webapp:beauty_appointment_list")
            except Exception as exc:
                messages.error(request, f"Couldn't book: {exc}")
    else:
        form = BookBeautyAppointmentForm(company=company)
    no_services = not BeautyService.objects.for_company(company).filter(is_active=True).exists()
    no_staff = not Employee.objects.for_company(company).filter(is_active=True).exists()
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/beauty_parlour/appointment_book.html", {
        "form": form, "no_services": no_services, "no_staff": no_staff, "no_customers": no_customers,
    })


@login_required
def beauty_appointment_complete(request, appointment_id):
    company = request.company
    appt = get_object_or_404(BeautyAppointment.objects.for_company(company), id=appointment_id)
    beauty_services.complete_appointment(appt)
    messages.success(request, "Marked completed.")
    return redirect("webapp:beauty_appointment_list")


@login_required
def beauty_appointment_cancel(request, appointment_id):
    company = request.company
    appt = get_object_or_404(BeautyAppointment.objects.for_company(company), id=appointment_id)
    beauty_services.cancel_appointment(appt)
    messages.success(request, "Cancelled.")
    return redirect("webapp:beauty_appointment_list")


@login_required
def beauty_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    appts = BeautyAppointment.objects.for_company(company)
    completed = appts.filter(status="completed")
    context = {
        "booked_count": appts.filter(status="booked").count(),
        "completed_count": completed.count(),
        "revenue": completed.aggregate(total=Sum("price"))["total"] or 0,
        "by_service": completed.values("service__name").annotate(count=Count("id"), revenue=Sum("price")).order_by("-revenue"),
    }
    return render(request, "webapp/beauty_parlour/reports.html", context)


# ================= MEDICAL SHOP =================

@login_required
def medicine_batch_list(request):
    company = request.company
    batches = (
        MedicineBatch.objects.for_company(company).select_related("product")
        .filter(quantity_remaining__gt=0).order_by("expiry_date")
        if company else []
    )
    return render(request, "webapp/medical_shop/batch_list.html", {"batches": batches})


@login_required
def medicine_batch_add(request):
    company = request.company
    if request.method == "POST":
        form = MedicineBatchForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            MedicineBatch.objects.create(
                company=company, product=d["product"], batch_number=d["batch_number"],
                manufacturer=d["manufacturer"], expiry_date=d["expiry_date"], received_date=d["received_date"],
                purchase_price=d["purchase_price"], selling_price=d["selling_price"],
                quantity_received=d["quantity_received"], quantity_remaining=d["quantity_received"],
            )
            messages.success(request, "Batch added.")
            return redirect("webapp:medicine_batch_list")
    else:
        form = MedicineBatchForm(company=company)
    return render(request, "webapp/medical_shop/batch_form.html", {"form": form})


@login_required
def medicine_dispense(request, batch_id):
    company = request.company
    batch = get_object_or_404(MedicineBatch.objects.for_company(company), id=batch_id)
    if request.method == "POST":
        form = DispenseForm(request.POST, company=company)
        if form.is_valid():
            try:
                medical_services.dispense(
                    batch, quantity=form.cleaned_data["quantity"], sold_price=form.cleaned_data["sold_price"],
                    sold_date=form.cleaned_data["sold_date"], customer=form.cleaned_data["customer"],
                    prescription_reference=form.cleaned_data["prescription_reference"],
                )
                messages.success(request, "Dispensed.")
                return redirect("webapp:medicine_batch_list")
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = DispenseForm(company=company, initial={"sold_date": tz.now().date()})
    return render(request, "webapp/medical_shop/dispense_form.html", {"form": form, "batch": batch})


@login_required
def medicine_dispense_history(request):
    company = request.company
    records = (
        DispenseRecord.objects.for_company(company).select_related("batch__product", "customer")
        .order_by("-sold_date")
        if company else []
    )
    return render(request, "webapp/medical_shop/dispense_history.html", {"records": records})


@login_required
def medical_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    records = DispenseRecord.objects.for_company(company).filter(is_returned=False)
    batches = MedicineBatch.objects.for_company(company)
    today = tz.now().date()
    context = {
        "revenue": records.aggregate(total=Sum("sold_price"))["total"] or 0,
        "batches_in_stock": batches.filter(quantity_remaining__gt=0).count(),
        "expiring_soon": batches.filter(quantity_remaining__gt=0, expiry_date__lte=today + timedelta(days=30), expiry_date__gte=today).count(),
        "expired": batches.filter(quantity_remaining__gt=0, expiry_date__lt=today).count(),
    }
    return render(request, "webapp/medical_shop/reports.html", context)


# ================= PROTEIN SHOP =================

@login_required
def protein_batch_list(request):
    company = request.company
    batches = (
        ProteinBatch.objects.for_company(company).select_related("product")
        .filter(quantity_remaining__gt=0).order_by("expiry_date")
        if company else []
    )
    return render(request, "webapp/protein_shop/batch_list.html", {"batches": batches})


@login_required
def protein_batch_add(request):
    company = request.company
    if request.method == "POST":
        form = ProteinBatchForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            ProteinBatch.objects.create(
                company=company, product=d["product"], batch_number=d["batch_number"], flavour=d["flavour"],
                weight_grams=d["weight_grams"], expiry_date=d["expiry_date"], received_date=d["received_date"],
                purchase_price=d["purchase_price"], selling_price=d["selling_price"],
                quantity_received=d["quantity_received"], quantity_remaining=d["quantity_received"],
            )
            messages.success(request, "Batch added.")
            return redirect("webapp:protein_batch_list")
    else:
        form = ProteinBatchForm(company=company)
    return render(request, "webapp/protein_shop/batch_form.html", {"form": form})


@login_required
def protein_sell(request, batch_id):
    company = request.company
    batch = get_object_or_404(ProteinBatch.objects.for_company(company), id=batch_id)
    if request.method == "POST":
        form = SellProteinForm(request.POST, company=company)
        if form.is_valid():
            try:
                protein_services.sell(
                    batch, quantity=form.cleaned_data["quantity"], sold_price=form.cleaned_data["sold_price"],
                    sold_date=form.cleaned_data["sold_date"], customer=form.cleaned_data["customer"],
                )
                messages.success(request, "Sold.")
                return redirect("webapp:protein_batch_list")
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = SellProteinForm(company=company, initial={"sold_date": tz.now().date()})
    return render(request, "webapp/protein_shop/sell_form.html", {"form": form, "batch": batch})


@login_required
def protein_sale_history(request):
    company = request.company
    records = (
        SaleRecord.objects.for_company(company).select_related("batch__product", "customer")
        .order_by("-sold_date")
        if company else []
    )
    return render(request, "webapp/protein_shop/sale_history.html", {"records": records})


@login_required
def protein_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    records = SaleRecord.objects.for_company(company).filter(is_returned=False)
    batches = ProteinBatch.objects.for_company(company)
    today = tz.now().date()
    context = {
        "revenue": records.aggregate(total=Sum("sold_price"))["total"] or 0,
        "batches_in_stock": batches.filter(quantity_remaining__gt=0).count(),
        "expiring_soon": batches.filter(quantity_remaining__gt=0, expiry_date__lte=today + timedelta(days=30), expiry_date__gte=today).count(),
        "expired": batches.filter(quantity_remaining__gt=0, expiry_date__lt=today).count(),
    }
    return render(request, "webapp/protein_shop/reports.html", context)


# ================= CONSTRUCTION =================

@login_required
@require_business_group("project", "construction")
def project_list(request):
    company = request.company
    projects = Project.objects.for_company(company).select_related("client").order_by("-start_date") if company else []
    return render(request, "webapp/construction/project_list.html", {"projects": projects})


@login_required
@require_business_group("project", "construction")
def project_add(request):
    company = request.company
    if request.method == "POST":
        form = ProjectForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            Project.objects.create(
                company=company, name=d["name"], client=d["client"], site_address=d["site_address"],
                start_date=d["start_date"], end_date=d["end_date"], budget=d["budget"],
                contract_value=d["contract_value"], status="planning",
            )
            messages.success(request, "Project created.")
            return redirect("webapp:project_list")
    else:
        form = ProjectForm(company=company, initial={"start_date": tz.now().date()})
    return render(request, "webapp/construction/project_form.html", {"form": form})


@login_required
@require_business_group("project", "construction")
def project_edit(request, project_id):
    company = request.company
    obj = get_object_or_404(Project.objects.for_company(company), id=project_id)
    if request.method == "POST":
        form = ProjectForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            obj.name = d["name"]; obj.client = d["client"]; obj.site_address = d["site_address"]
            obj.start_date = d["start_date"]; obj.end_date = d["end_date"]
            obj.budget = d["budget"]; obj.contract_value = d["contract_value"]
            if d["status"]:
                obj.status = d["status"]
            obj.save()
            messages.success(request, "Project updated.")
            return redirect("webapp:project_detail", project_id=obj.id)
    else:
        form = ProjectForm(company=company, initial={
            "name": obj.name, "client": obj.client_id, "site_address": obj.site_address,
            "start_date": obj.start_date, "end_date": obj.end_date, "budget": obj.budget,
            "contract_value": obj.contract_value, "status": obj.status,
        })
    return render(request, "webapp/construction/project_form.html", {"form": form, "editing": True})


@login_required
@require_business_group("project", "construction")
def project_detail(request, project_id):
    company = request.company
    project = get_object_or_404(Project.objects.for_company(company), id=project_id)
    summary = construction_services.project_summary(project)
    expenses = ProjectExpense.objects.filter(project=project).select_related("contractor").order_by("-date")
    return render(request, "webapp/construction/project_detail.html", {
        "project": project, "summary": summary, "expenses": expenses,
        "milestones": project.milestones.order_by("due_date"),
        "tasks": project.tasks.select_related("assigned_to", "milestone").order_by("due_date"),
        "timesheets": project.timesheets.select_related("employee", "task").order_by("-date")[:20],
        "labour_cost": sum((row.cost for row in project.timesheets.all()), Decimal("0")),
    })


@login_required
@require_business_group("project", "construction")
def project_milestone_add(request, project_id):
    project = get_object_or_404(Project.objects.for_company(request.company), id=project_id)
    form = ProjectMilestoneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.project = project; obj.save()
        messages.success(request, "Milestone added."); return redirect("webapp:project_detail", project_id=project.id)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": f"Milestone — {project.name}", "cancel_url": "webapp:project_detail", "cancel_id": project.id})


@login_required
@require_business_group("project", "construction")
def project_task_add(request, project_id):
    project = get_object_or_404(Project.objects.for_company(request.company), id=project_id)
    form = ProjectTaskForm(request.POST or None, company=request.company, project=project)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.project = project; obj.save()
        messages.success(request, "Task added."); return redirect("webapp:project_detail", project_id=project.id)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": f"Task — {project.name}", "cancel_url": "webapp:project_detail", "cancel_id": project.id})


@login_required
@require_business_group("project", "construction")
def project_timesheet_add(request, project_id):
    project = get_object_or_404(Project.objects.for_company(request.company), id=project_id)
    form = ProjectTimesheetForm(request.POST or None, company=request.company, project=project, initial={"date": tz.now().date()})
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.project = project; obj.save()
        messages.success(request, "Timesheet recorded."); return redirect("webapp:project_detail", project_id=project.id)
    return render(request, "webapp/mobile_shop/form.html", {"form": form, "heading": f"Timesheet — {project.name}", "cancel_url": "webapp:project_detail", "cancel_id": project.id})


@login_required
def contractor_list(request):
    company = request.company
    contractors = Contractor.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/construction/contractor_list.html", {"contractors": contractors})


@login_required
def contractor_add(request):
    company = request.company
    if request.method == "POST":
        form = ContractorForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Contractor added.")
            return redirect("webapp:contractor_list")
    else:
        form = ContractorForm(company=company)
    return render(request, "webapp/construction/contractor_form.html", {"form": form})


@login_required
def contractor_edit(request, contractor_id):
    company = request.company
    obj = get_object_or_404(Contractor.objects.for_company(company), id=contractor_id)
    if request.method == "POST":
        form = ContractorForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Contractor updated.")
            return redirect("webapp:contractor_list")
    else:
        form = ContractorForm(instance=obj, company=company)
    return render(request, "webapp/construction/contractor_form.html", {"form": form, "editing": True})


@login_required
def contractor_delete(request, contractor_id):
    company = request.company
    obj = get_object_or_404(Contractor.objects.for_company(company), id=contractor_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Contractor deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this contractor has expenses linked to them.")
        return redirect("webapp:contractor_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:contractor_list", "delete_url": "webapp:contractor_delete", "delete_id": contractor_id,
    })


@login_required
def project_expense_add(request):
    company = request.company
    if request.method == "POST":
        form = ProjectExpenseForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            try:
                construction_services.record_project_expense(
                    company=company, user=request.user, project=d["project"], category=d["category"],
                    date=d["date"], amount=d["amount"], description=d["description"],
                    payment_method=d["payment_method"], contractor=d["contractor"],
                )
                messages.success(request, "Expense recorded.")
                return redirect("webapp:project_detail", project_id=d["project"].id)
            except Exception as exc:
                messages.error(request, f"Couldn't record expense: {exc}")
    else:
        form = ProjectExpenseForm(company=company, initial={"date": tz.now().date()})
    no_projects = not Project.objects.for_company(company).exists()
    return render(request, "webapp/construction/expense_form.html", {"form": form, "no_projects": no_projects})


@login_required
def construction_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")
    projects = Project.objects.for_company(company)
    context = {
        "planning_count": projects.filter(status="planning").count(),
        "active_count": projects.filter(status="active").count(),
        "completed_count": projects.filter(status="completed").count(),
        "total_contract_value": projects.aggregate(total=Sum("contract_value"))["total"] or 0,
    }
    return render(request, "webapp/construction/reports.html", context)


# ================= GENERIC RETAIL (Watch / Perfume / Book Store) =================

@login_required
def retail_sale_list(request):
    company = request.company
    invoices = (
        SalesInvoice.objects.for_company(company).select_related("customer").order_by("-date")
        if company else []
    )
    return render(request, "webapp/retail/sale_list.html", {"invoices": invoices})


@login_required
def retail_sale_add(request):
    company = request.company
    if request.method == "POST":
        form = RetailSaleForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            try:
                sales_services.create_invoice(
                    company=company, user=request.user, customer=d["customer"], date=d["date"],
                    warehouse=_default_warehouse(company),
                    lines=[{"product": d["product"], "quantity": d["quantity"], "unit_price": d["unit_price"]}],
                )
                messages.success(request, "Sale recorded.")
                return redirect("webapp:retail_sale_list")
            except Exception as exc:
                messages.error(request, f"Couldn't record sale: {exc}")
    else:
        form = RetailSaleForm(company=company, initial={"date": tz.now().date()})
    no_products = not Product.objects.for_company(company).filter(is_active=True).exists()
    no_customers = not Customer.objects.for_company(company).exists()
    return render(request, "webapp/retail/sale_form.html", {
        "form": form, "no_products": no_products, "no_customers": no_customers,
    })


@login_required
def retail_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    from calendar import monthrange
    from datetime import date
    from decimal import Decimal

    period = request.GET.get("period", "month")
    today = tz.now().date()
    try:
        selected_date = date.fromisoformat(request.GET.get("date", today.isoformat()))
    except ValueError:
        selected_date = today

    invoices = SalesInvoice.objects.for_company(company).exclude(status="void")
    if period == "day":
        invoices = invoices.filter(date=selected_date)
        period_label = selected_date.strftime("%d %b %Y")
    elif period == "month":
        last_day = monthrange(selected_date.year, selected_date.month)[1]
        invoices = invoices.filter(
            date__range=(selected_date.replace(day=1), selected_date.replace(day=last_day))
        )
        period_label = selected_date.strftime("%B %Y")
    else:
        period = "all"
        period_label = "All time"

    lines = SalesInvoiceLine.objects.filter(invoice__in=invoices).select_related(
        "product", "product__category"
    )
    revenue = invoices.aggregate(total=Sum("total"))["total"] or Decimal("0")
    cost_of_goods = sum(
        (line.quantity * line.product.cost_price for line in lines), Decimal("0")
    )
    context = {
        "revenue": revenue,
        "cost_of_goods": cost_of_goods,
        "gross_profit": revenue - cost_of_goods,
        "invoice_count": invoices.count(),
        "period": period,
        "selected_date": selected_date.isoformat(),
        "period_label": period_label,
        "top_products": (
            lines.values("product__name", "product__variant_label", "product__size", "product__colour")
            .annotate(units_sold=Sum("quantity"), revenue=Sum("line_total"))
            .order_by("-revenue")[:8]
        ),
        "top_categories": (
            lines.values("product__category__name")
            .annotate(units_sold=Sum("quantity"), revenue=Sum("line_total"))
            .order_by("-revenue")[:8]
        ),
        "top_sizes": (
            lines.exclude(product__size="").values("product__size")
            .annotate(units_sold=Sum("quantity"), revenue=Sum("line_total"))
            .order_by("-units_sold")[:8]
        ),
        "top_colours": (
            lines.exclude(product__colour="").values("product__colour")
            .annotate(units_sold=Sum("quantity"), revenue=Sum("line_total"))
            .order_by("-units_sold")[:8]
        ),
    }
    return render(request, "webapp/retail/reports.html", context)


# ================= RESTAURANT / CAFE / CATERING =================

@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_dashboard(request):
    company = request.company
    today = timezone.localdate()
    orders = list(
        RestaurantOrder.objects.for_company(company).exclude(status__in=["paid", "cancelled"])
        .select_related("table", "customer").prefetch_related("lines__modifiers")[:30]
    )
    paid_today = RestaurantOrder.objects.for_company(company).filter(status="paid", invoice__date=today)
    tables = DiningTable.objects.for_company(company).filter(is_active=True)
    open_order_by_table = {o.table_id: o for o in orders if o.table_id}
    areas = list(DiningArea.objects.for_company(company).prefetch_related("tables"))
    for area in areas:
        for table in area.tables.all():
            table.open_order = open_order_by_table.get(table.id)
    return render(request, "webapp/restaurant/dashboard.html", {
        "areas": areas,
        "orders": orders,
        "open_shift": RestaurantShift.objects.for_company(company).filter(status="open").first(),
        "recent_shifts": RestaurantShift.objects.for_company(company).order_by("-opened_at")[:10],
        "stats": {
            "sales_today": paid_today.aggregate(total=Sum("invoice__total"))["total"] or Decimal("0"),
            "paid_today": paid_today.count(),
            "active_orders": len(orders),
            "in_kitchen": KitchenTicket.objects.for_company(company).filter(status__in=["queued", "preparing"]).count(),
            "tables_busy": tables.filter(status="occupied").count(),
            "tables_total": tables.count(),
        },
    })


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_area_add(request):
    form = DiningAreaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.save()
        messages.success(request, "Dining area added.")
        return redirect("webapp:restaurant_dashboard")
    return render(request, "webapp/platform_admin/simple_form.html", {"form": form, "form_title": "Add dining area", "cancel_url": "webapp:restaurant_dashboard"})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_table_add(request):
    form = DiningTableForm(request.POST or None, company=request.company)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.save()
        messages.success(request, "Dining table added.")
        return redirect("webapp:restaurant_dashboard")
    return render(request, "webapp/platform_admin/simple_form.html", {"form": form, "form_title": "Add dining table", "cancel_url": "webapp:restaurant_dashboard"})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_table_status(request, table_id):
    table = get_object_or_404(DiningTable.objects.for_company(request.company), id=table_id)
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    status = request.POST.get("status")
    has_open_order = RestaurantOrder.objects.for_company(request.company).filter(table=table).exclude(status__in=["paid", "cancelled"]).exists()
    if status not in {"available", "cleaning", "reserved"}:
        messages.error(request, "Unknown table status.")
    elif has_open_order:
        messages.error(request, f"Table {table.name} still has an open order.")
    else:
        table.status = status
        table.save(update_fields=["status"])
        messages.success(request, f"Table {table.name} is now {table.get_status_display().lower()}.")
    return redirect("webapp:restaurant_dashboard")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_setup(request):
    company = request.company
    profile, _ = RestaurantProfile.objects.get_or_create(company=company)
    return render(request, "webapp/restaurant/setup.html", {
        "modifiers": MenuModifier.objects.for_company(company),
        "menu_items": RestaurantMenuItem.objects.for_company(company).select_related("product", "product__category"),
        "recipes": RecipeIngredient.objects.for_company(company).select_related("menu_product", "ingredient_product"),
        "combos": RestaurantCombo.objects.for_company(company).prefetch_related("items__product"),
        "integrations": DeliveryIntegration.objects.for_company(company),
        "imports": DeliveryOrderImport.objects.for_company(company).select_related("integration", "restaurant_order")[:20],
        "modifier_groups": MenuModifierGroup.objects.for_company(company).prefetch_related("options__modifier"),
        "stations": KitchenStation.objects.for_company(company).prefetch_related("categories"),
        "profile": profile,
    })


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_menu_item_form(request, menu_item_id=None):
    menu_item = get_object_or_404(
        RestaurantMenuItem.objects.for_company(request.company), id=menu_item_id
    ) if menu_item_id else None
    form = RestaurantMenuItemForm(
        request.POST or None, request.FILES or None, instance=menu_item, company=request.company
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Menu item saved with photo and availability settings.")
        return redirect("webapp:restaurant_setup")
    return render(request, "webapp/restaurant/menu_item_form.html", {"form": form, "menu_item": menu_item})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_demo_menu(request):
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    from django.core.management import call_command
    try:
        call_command("seed_restaurant_demo", company_slug=request.company.slug)
        messages.success(request, "20 sample dishes with illustrations are ready. Review names and prices before serving.")
    except Exception as exc:
        messages.error(request, f"Could not add sample menu: {exc}")
    order_id = request.POST.get("order_id")
    if order_id and RestaurantOrder.objects.for_company(request.company).filter(pk=order_id).exists():
        return redirect("webapp:restaurant_order_detail", order_id=order_id)
    return redirect("webapp:restaurant_setup")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_menu_item_toggle(request, menu_item_id):
    item = get_object_or_404(RestaurantMenuItem.objects.for_company(request.company), id=menu_item_id)
    if request.method == "POST":
        item.is_available = not item.is_available
        item.save(update_fields=["is_available"])
        messages.success(request, f"{item.product.name} marked {'available' if item.is_available else 'sold out'}.")
    return redirect(request.POST.get("next") or "webapp:restaurant_setup")


def _restaurant_setup_form(request, form_class, title):
    company_forms = {RecipeIngredientForm, RestaurantComboForm, RestaurantComboItemForm, MenuModifierOptionForm, KitchenStationForm}
    form = form_class(request.POST or None, company=request.company) if form_class in company_forms else form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.save()
        messages.success(request, f"{title} saved.")
        return redirect("webapp:restaurant_setup")
    return render(request, "webapp/platform_admin/simple_form.html", {"form": form, "form_title": title, "cancel_url": "webapp:restaurant_setup"})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_modifier_add(request): return _restaurant_setup_form(request, MenuModifierForm, "Add menu modifier")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_modifier_group_add(request): return _restaurant_setup_form(request, MenuModifierGroupForm, "Add modifier group")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_modifier_option_add(request): return _restaurant_setup_form(request, MenuModifierOptionForm, "Add option to modifier group")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_station_add(request): return _restaurant_setup_form(request, KitchenStationForm, "Add kitchen station")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_profile_edit(request):
    profile, _ = RestaurantProfile.objects.get_or_create(company=request.company)
    form = RestaurantProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.save()
        messages.success(request, "Restaurant public menu settings saved.")
        return redirect("webapp:restaurant_setup")
    return render(request, "webapp/platform_admin/simple_form.html", {"form": form, "form_title": "Restaurant & QR menu settings", "cancel_url": "webapp:restaurant_setup"})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_recipe_add(request): return _restaurant_setup_form(request, RecipeIngredientForm, "Add recipe ingredient")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_combo_add(request): return _restaurant_setup_form(request, RestaurantComboForm, "Add combo meal")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_combo_item_add(request): return _restaurant_setup_form(request, RestaurantComboItemForm, "Add combo item")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_integration_form(request, integration_id=None):
    integration = get_object_or_404(DeliveryIntegration.objects.for_company(request.company), id=integration_id) if integration_id else None
    form = DeliveryIntegrationForm(request.POST or None, instance=integration)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = request.company; obj.save()
        messages.success(request, "Delivery integration settings saved securely.")
        return redirect("webapp:restaurant_setup")
    return render(request, "webapp/restaurant/integration_form.html", {"form": form, "integration": integration})


@csrf_exempt
def restaurant_delivery_webhook(request, webhook_token):
    import json
    from django.http import JsonResponse
    if request.method != "POST": return JsonResponse({"error": "POST required"}, status=405)
    integration = get_object_or_404(DeliveryIntegration._base_manager.select_related("company"), webhook_token=webhook_token, is_enabled=True)
    signature = request.META.get("HTTP_X_DELIVERY_SIGNATURE", "")
    if not restaurant_services.verify_delivery_webhook(integration, request.body, signature):
        return JsonResponse({"error": "Invalid signature"}, status=401)
    try: payload = json.loads(request.body)
    except ValueError: return JsonResponse({"error": "Invalid JSON"}, status=400)
    log = restaurant_services.import_delivery_order(integration=integration, payload=payload)
    return JsonResponse({"status": log.status, "external_order_id": log.external_order_id}, status=200 if log.status == "imported" else 422)


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_order_add(request):
    company = request.company
    initial = {}
    if request.GET.get("table"):
        initial = {"channel": "dine_in", "table": request.GET.get("table")}
    elif request.GET.get("channel") in dict(RestaurantOrder.CHANNELS):
        initial = {"channel": request.GET["channel"]}
    form = RestaurantOrderForm(request.POST or None, company=company, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        order = restaurant_services.create_order(
            company=company, channel=d["channel"], table=d.get("table"), customer=d.get("customer"),
            waiter=request.user, shift=RestaurantShift.objects.for_company(company).filter(status="open").first(),
            delivery_address=d.get("delivery_address", ""), delivery_phone=d.get("delivery_phone", ""),
            guests=d.get("guests") or 0,
        )
        return redirect("webapp:restaurant_order_detail", order_id=order.id)
    return render(request, "webapp/restaurant/new_order.html", {
        "form": form,
        "tables": DiningTable.objects.for_company(company).filter(is_active=True).select_related("area"),
    })


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_order_detail(request, order_id):
    company = request.company
    order = get_object_or_404(RestaurantOrder.objects.for_company(company), id=order_id)
    if not Warehouse.objects.for_company(company).filter(is_active=True).exists():
        # Billing needs an active stock location; tenants created before
        # onboarding provisioned one would otherwise be unable to take payment.
        Warehouse.objects.create(company=company, name="Main Branch", is_active=True,
                                 is_default=not Warehouse.objects.for_company(company).filter(is_default=True).exists())
    line_form = RestaurantOrderLineForm(company=company)
    settle_form = RestaurantSettleForm(company=company, initial={"cash": order.total})
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "add_line":
                line_form = RestaurantOrderLineForm(request.POST, company=company)
                if line_form.is_valid():
                    d = line_form.cleaned_data
                    restaurant_services.add_order_line(company=company, order=order, product=d["product"], quantity=d["quantity"], unit_price=d.get("unit_price"), notes=d.get("notes", ""), modifiers=d.get("modifiers", ()))
                    messages.success(request, "Item added.")
                    return redirect("webapp:restaurant_order_detail", order_id=order.id)
            elif action == "quick_add":
                product = get_object_or_404(Product.objects.for_company(company), id=request.POST.get("product_id"))
                menu_item = get_object_or_404(RestaurantMenuItem.objects.for_company(company), product=product)
                if not menu_item.is_available:
                    raise ValueError("This menu item is currently sold out.")
                modifier_ids = request.POST.getlist("modifiers")
                modifiers = MenuModifier.objects.for_company(company).filter(id__in=modifier_ids, is_active=True)
                restaurant_services.add_order_line(
                    company=company, order=order, product=product,
                    quantity=request.POST.get("quantity") or 1,
                    notes=request.POST.get("notes", ""), modifiers=modifiers,
                )
                return redirect("webapp:restaurant_order_detail", order_id=order.id)
            elif action in {"increase_line", "decrease_line", "remove_line"}:
                line = get_object_or_404(RestaurantOrderLine.objects.for_company(company), id=request.POST.get("line_id"), order=order)
                if action == "remove_line":
                    restaurant_services.remove_order_line(company=company, line=line)
                else:
                    delta = Decimal("1") if action == "increase_line" else Decimal("-1")
                    restaurant_services.update_order_line_quantity(company=company, line=line, quantity=line.quantity + delta)
                return redirect("webapp:restaurant_order_detail", order_id=order.id)
            elif action == "send_kitchen":
                if not order.lines.filter(sent_at__isnull=True).exists():
                    messages.error(request, "Add at least one new menu item before sending to the kitchen.")
                    return redirect("webapp:restaurant_order_detail", order_id=order.id)
                ticket = restaurant_services.send_to_kitchen(company=company, order=order)
                messages.success(request, f"KOT sent to kitchen (round {ticket.kitchen_round}).")
                return redirect(reverse("webapp:restaurant_order_detail", args=[order.id]) + f"?sent={ticket.id}")
            elif action == "transfer":
                table = get_object_or_404(DiningTable.objects.for_company(company), id=request.POST.get("table_id"))
                restaurant_services.transfer_table(company=company, order=order, table=table)
                messages.success(request, f"Order moved to table {table.name}.")
                return redirect("webapp:restaurant_order_detail", order_id=order.id)
            elif action == "guests":
                order.guests = max(0, min(500, int(request.POST.get("guests") or 0)))
                order.save(update_fields=["guests"])
                messages.success(request, "Guest count updated.")
                return redirect("webapp:restaurant_order_detail", order_id=order.id)
            elif action in {"hold", "resume"}:
                restaurant_services.set_order_held(company=company, order=order, held=action == "hold")
                return redirect("webapp:restaurant_order_detail", order_id=order.id)
            elif action == "split":
                new_order = restaurant_services.split_order(company=company, order=order, line_ids=request.POST.getlist("line_ids"))
                messages.success(request, f"Split into {new_order.order_number}.")
                return redirect("webapp:restaurant_order_detail", order_id=new_order.id)
            elif action == "merge":
                source = get_object_or_404(RestaurantOrder.objects.for_company(company), id=request.POST.get("source_order_id"))
                restaurant_services.merge_orders(company=company, target=order, source=source)
                messages.success(request, "Orders merged.")
                return redirect("webapp:restaurant_order_detail", order_id=order.id)
            elif action == "settle":
                settle_form = RestaurantSettleForm(request.POST, company=company)
                if settle_form.is_valid():
                    d = settle_form.cleaned_data
                    order.service_charge = d.get("service_charge") or 0; order.tip_amount = d.get("tip_amount") or 0; order.discount_amount = d.get("discount_amount") or 0
                    order.save(update_fields=["service_charge", "tip_amount", "discount_amount"])
                    payments = [{"method": method, "amount": d.get(method) or 0} for method in ("cash", "card", "bank") if (d.get(method) or 0) > 0]
                    restaurant_services.settle_order(company=company, user=request.user, order=order, warehouse=d["warehouse"], date=timezone.localdate(), payments=payments)
                    messages.success(request, "Order billed and paid.")
                    return redirect("webapp:restaurant_dashboard")
        except Exception as exc:
            messages.error(request, str(exc))
    merge_candidates = RestaurantOrder.objects.for_company(company).exclude(id=order.id).exclude(status__in=["paid", "cancelled"])
    menu_items = RestaurantMenuItem.objects.for_company(company).select_related(
        "product", "product__category"
    ).prefetch_related("modifier_groups__options__modifier").filter(product__is_active=True).order_by("sort_order", "product__name")
    categories = ProductCategory.objects.for_company(company).filter(
        product__restaurant_menu_item__isnull=False
    ).distinct().order_by("name")
    profile = RestaurantProfile.objects.for_company(company).first()
    service_pct = profile.service_charge_percent if profile else Decimal("0")
    suggested_service = order.service_charge
    if not suggested_service and order.channel == "dine_in" and service_pct:
        suggested_service = (order.subtotal * service_pct / Decimal("100")).quantize(Decimal("0.01"))
    busy_table_ids = RestaurantOrder.objects.for_company(company).exclude(status__in=["paid", "cancelled"]).exclude(table=None).values_list("table_id", flat=True)
    return render(request, "webapp/restaurant/order_detail.html", {
        "order": order, "line_form": line_form, "settle_form": settle_form,
        "unsent_count": order.lines.filter(sent_at__isnull=True).count(),
        "free_tables": DiningTable.objects.for_company(company).filter(is_active=True).exclude(id__in=list(busy_table_ids)).select_related("area"),
        "suggested_service": suggested_service, "service_pct": service_pct,
        "merge_candidates": merge_candidates, "menu_items": menu_items,
        "menu_categories": categories,
        "active_modifiers": MenuModifier.objects.for_company(company).filter(is_active=True),
    })


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_kitchen(request):
    tickets = list(KitchenTicket.objects.for_company(request.company).exclude(status="served")
                   .select_related("order", "order__table", "station")
                   .prefetch_related("order__lines__product__category", "order__lines__modifiers__modifier", "station__categories")
                   .order_by("-priority", "printed_at"))
    return render(request, "webapp/restaurant/kitchen.html", {
        "tickets": tickets,
        "queued_count": sum(t.status == "queued" for t in tickets),
        "preparing_count": sum(t.status == "preparing" for t in tickets),
        "ready_count": sum(t.status == "ready" for t in tickets),
    })


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_kitchen_status(request, ticket_id, status):
    ticket = get_object_or_404(KitchenTicket.objects.for_company(request.company), id=ticket_id)
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    try:
        restaurant_services.update_kitchen_status(company=request.company, ticket=ticket, status=status)
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("webapp:restaurant_kitchen")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_shift_open(request):
    form = RestaurantShiftOpenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        restaurant_services.open_shift(company=request.company, user=request.user, opening_cash=form.cleaned_data["opening_cash"])
        return redirect("webapp:restaurant_dashboard")
    return render(request, "webapp/platform_admin/simple_form.html", {"form": form, "form_title": "Open restaurant shift", "cancel_url": "webapp:restaurant_dashboard"})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_shift_close(request, shift_id):
    shift = get_object_or_404(RestaurantShift.objects.for_company(request.company), id=shift_id)
    form = RestaurantShiftCloseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        restaurant_services.close_shift(company=request.company, user=request.user, shift=shift, actual_cash=form.cleaned_data["actual_cash"])
        return redirect("webapp:restaurant_dashboard")
    return render(request, "webapp/platform_admin/simple_form.html", {"form": form, "form_title": "Close restaurant shift", "cancel_url": "webapp:restaurant_dashboard"})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_reservations(request):
    company = request.company
    form = TableReservationForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.company = company; obj.save()
        messages.success(request, "Reservation saved.")
        return redirect("webapp:restaurant_reservations")
    reservations = TableReservation.objects.for_company(company).select_related("table", "table__area")
    return render(request, "webapp/restaurant/reservations.html", {"form": form, "reservations": reservations[:100]})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_reservation_status(request, reservation_id, status):
    reservation = get_object_or_404(TableReservation.objects.for_company(request.company), id=reservation_id)
    allowed = {x[0] for x in TableReservation.STATUS}
    if request.method == "POST" and status in allowed:
        reservation.status = status; reservation.save(update_fields=["status"])
        if reservation.table and status == "seated":
            reservation.table.status = "occupied"; reservation.table.save(update_fields=["status"])
    return redirect("webapp:restaurant_reservations")


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_waste(request):
    company = request.company
    form = FoodWasteForm(request.POST or None, company=company)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        restaurant_services.record_food_waste(company=company, user=request.user, **d)
        messages.success(request, "Food waste recorded and ingredient stock adjusted.")
        return redirect("webapp:restaurant_waste")
    waste = FoodWaste.objects.for_company(company).select_related("ingredient", "warehouse", "recorded_by")[:100]
    return render(request, "webapp/restaurant/waste.html", {"form": form, "waste_rows": waste})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_reports(request):
    from datetime import date
    today = timezone.localdate()
    try: start = date.fromisoformat(request.GET.get("from", today.replace(day=1).isoformat()))
    except ValueError: start = today.replace(day=1)
    try: end = date.fromisoformat(request.GET.get("to", today.isoformat()))
    except ValueError: end = today
    orders = RestaurantOrder.objects.for_company(request.company).filter(status="paid", created_at__date__range=(start, end))
    lines = RestaurantOrderLine.objects.for_company(request.company).filter(order__in=orders).select_related("product", "product__category")
    revenue = sum((o.total for o in orders.prefetch_related("lines__modifiers")), Decimal("0"))
    food_cost = sum((line.quantity * sum((r.quantity * r.ingredient_product.cost_price for r in line.product.restaurant_recipe.select_related("ingredient_product")), Decimal("0")) for line in lines), Decimal("0"))
    channel_sales = orders.values("channel").annotate(total=Sum("invoice__total"), orders=Count("id")).order_by("channel")
    top_items = lines.values("product__name").annotate(
        qty_sold=Sum("quantity"),
        total=Sum(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=18, decimal_places=2)),
    ).order_by("-total")[:15]
    waste_cost = sum((x.quantity * x.ingredient.cost_price for x in FoodWaste.objects.for_company(request.company).filter(recorded_at__date__range=(start, end)).select_related("ingredient")), Decimal("0"))
    return render(request, "webapp/restaurant/reports.html", {"start": start, "end": end, "revenue": revenue, "food_cost": food_cost, "gross_margin": revenue-food_cost, "waste_cost": waste_cost, "order_count": orders.count(), "channel_sales": channel_sales, "top_items": top_items})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_receipt_print(request, order_id):
    order = get_object_or_404(RestaurantOrder.objects.for_company(request.company).select_related("customer", "table", "invoice").prefetch_related("lines__modifiers__modifier"), id=order_id)
    return render(request, "webapp/restaurant/receipt_print.html", {"order": order})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_kot_print(request, ticket_id):
    ticket = get_object_or_404(KitchenTicket.objects.for_company(request.company).select_related("order", "station", "order__table").prefetch_related("order__lines__product", "order__lines__modifiers__modifier"), id=ticket_id)
    return render(request, "webapp/restaurant/kot_print.html", {"ticket": ticket})


def restaurant_public_menu(request, token):
    profile = get_object_or_404(RestaurantProfile.objects.select_related("company"), public_menu_token=token)
    items = [x for x in RestaurantMenuItem.objects.for_company(profile.company).filter(is_available=True, product__is_active=True).select_related("product", "product__category").prefetch_related("modifier_groups__options__modifier") if x.is_orderable_now()]
    categories = ProductCategory.objects.for_company(profile.company).filter(product__restaurant_menu_item__is_available=True).distinct().order_by("name")
    tables = DiningTable.objects.for_company(profile.company).filter(is_active=True, status="available").select_related("area")
    return render(request, "webapp/restaurant/public_menu.html", {"profile": profile, "restaurant": profile.company, "menu_items": items, "categories": categories, "tables": tables})


def restaurant_public_menu_qr(request, token):
    import io, qrcode
    get_object_or_404(RestaurantProfile, public_menu_token=token)
    target = request.build_absolute_uri(reverse("webapp:restaurant_public_menu", args=[token]))
    image = qrcode.make(target)
    output = io.BytesIO(); image.save(output, format="PNG")
    return HttpResponse(output.getvalue(), content_type="image/png")


def restaurant_public_order(request, token):
    import json, uuid
    from django.core.cache import cache
    from django.http import JsonResponse
    if request.method != "POST": return JsonResponse({"error": "POST required"}, status=405)
    profile = get_object_or_404(RestaurantProfile.objects.select_related("company"), public_menu_token=token)
    if not profile.qr_ordering_enabled:
        return JsonResponse({"error": "Self-ordering is not enabled."}, status=403)
    ip = request.META.get("REMOTE_ADDR", "unknown")
    throttle_key = f"qr-order:{profile.id}:{ip}"
    attempts = cache.get(throttle_key, 0)
    if attempts >= 10: return JsonResponse({"error": "Too many orders. Please ask a staff member."}, status=429)
    cache.set(throttle_key, attempts + 1, 60)
    try:
        payload = json.loads(request.body)
        raw_items = payload.get("items") or []
        if not raw_items or len(raw_items) > 50: raise ValueError("Select at least one valid menu item.")
        table = None
        if payload.get("table_id"):
            table = DiningTable.objects.for_company(profile.company).filter(id=payload["table_id"], is_active=True, status="available").first()
            if not table: raise ValueError("The selected table is no longer available.")
        channel = "dine_in" if table else "takeaway"
        customer = None
        phone = str(payload.get("phone", ""))[:30].strip()
        name = str(payload.get("name", ""))[:150].strip()
        if phone or name:
            customer = Customer.objects.for_company(profile.company).filter(phone=phone).first() if phone else None
            if not customer: customer = Customer.objects.create(company=profile.company, name=name or "QR Menu Guest", phone=phone)
        with transaction.atomic():
            order = restaurant_services.create_order(
                company=profile.company, channel=channel, table=table, customer=customer,
                shift=RestaurantShift.objects.for_company(profile.company).filter(status="open").first(),
            )
            order.public_order_token = uuid.uuid4(); order.save(update_fields=["public_order_token"])
            for row in raw_items:
                menu_item = get_object_or_404(RestaurantMenuItem.objects.for_company(profile.company).select_related("product"), product_id=row.get("product_id"))
                if not menu_item.is_orderable_now(): raise ValueError(f"{menu_item.product.name} is not currently available.")
                modifier_ids = row.get("modifier_ids") or []
                modifiers = MenuModifier.objects.for_company(profile.company).filter(id__in=modifier_ids, is_active=True)
                restaurant_services.add_order_line(company=profile.company, order=order, product=menu_item.product, quantity=row.get("quantity", 1), notes=str(row.get("notes", ""))[:255], modifiers=modifiers)
            restaurant_services.send_to_kitchen(company=profile.company, order=order)
        return JsonResponse({"order_number": order.order_number, "status_url": reverse("webapp:restaurant_public_order_status", args=[order.public_order_token])})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)


def restaurant_public_order_status(request, order_token):
    order = get_object_or_404(RestaurantOrder.objects.select_related("company", "table"), public_order_token=order_token)
    profile = RestaurantProfile.objects.for_company(order.company).first()
    return render(request, "webapp/restaurant/public_order_status.html", {"order": order, "profile": profile})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_order_cancel(request, order_id):
    order = get_object_or_404(RestaurantOrder.objects.for_company(request.company), id=order_id)
    if request.method == "POST":
        try:
            restaurant_services.cancel_order(company=request.company, user=request.user, order=order, reason=request.POST.get("reason", ""))
            messages.success(request, "Order cancelled with an audit record.")
            return redirect("webapp:restaurant_dashboard")
        except Exception as exc: messages.error(request, str(exc))
    return render(request, "webapp/restaurant/order_cancel.html", {"order": order})


@login_required
@require_business_group("restaurant")
@require_permission("restaurant.manage")
def restaurant_z_report(request, shift_id):
    shift = get_object_or_404(RestaurantShift.objects.for_company(request.company), id=shift_id)
    payments = shift.orders.filter(status="paid").values("payment_splits__method").annotate(total=Sum("payment_splits__amount"))
    orders = shift.orders.filter(status="paid").prefetch_related("lines__modifiers")
    gross_sales = sum((o.total for o in orders), Decimal("0"))
    cancelled = shift.orders.filter(status="cancelled").count()
    discounts = orders.aggregate(total=Sum("discount_amount"))["total"] or Decimal("0")
    tips = orders.aggregate(total=Sum("tip_amount"))["total"] or Decimal("0")
    return render(request, "webapp/restaurant/z_report.html", {"shift": shift, "payments": payments, "orders": orders, "gross_sales": gross_sales, "cancelled": cancelled, "discounts": discounts, "tips": tips})


# ================= INVOICE PDF (shared across verticals) =================

@login_required
def invoice_pdf(request, invoice_id):
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    company = request.company
    invoice = get_object_or_404(
        SalesInvoice.objects.for_company(company).select_related("customer"), id=invoice_id
    )
    lines = SalesInvoiceLine.objects.filter(invoice=invoice).select_related("product")

    html = render_to_string("webapp/invoice_pdf.html", {
        "company": company, "invoice": invoice, "lines": lines,
        "mobile_units": invoice.mobile_units.select_related("product").all(),
        "balance_due": invoice.total - invoice.amount_paid,
    })

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
    except Exception:
        # weasyprint isn't installed / failed to render — fall back to the printable HTML page
        return HttpResponse(html)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{invoice.invoice_number}.pdf"'
    return response


# ================= SUPPLIERS & PURCHASES (shared) =================

@login_required
@require_feature("webui_suppliers_purchases")
def supplier_list(request):
    company = request.company
    suppliers = Supplier.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/purchases/supplier_list.html", {"suppliers": suppliers})


@login_required
@require_permission("suppliers.manage")
def supplier_add(request):
    company = request.company
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Supplier added.")
            return redirect("webapp:supplier_list")
    else:
        form = SupplierForm()
    return render(request, "webapp/purchases/supplier_form.html", {"form": form})


@login_required
@require_permission("suppliers.manage")
def supplier_edit(request, supplier_id):
    company = request.company
    obj = get_object_or_404(Supplier.objects.for_company(company), id=supplier_id)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Supplier updated.")
            return redirect("webapp:supplier_list")
    else:
        form = SupplierForm(instance=obj)
    return render(request, "webapp/purchases/supplier_form.html", {"form": form, "editing": True})


@login_required
@require_permission("suppliers.manage")
def supplier_delete(request, supplier_id):
    company = request.company
    obj = get_object_or_404(Supplier.objects.for_company(company), id=supplier_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Supplier deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this supplier has purchases linked to them.")
        return redirect("webapp:supplier_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:supplier_list", "delete_url": "webapp:supplier_delete", "delete_id": supplier_id,
    })


@login_required
@require_feature("webui_suppliers_purchases")
def supplier_detail(request, supplier_id):
    company = request.company
    supplier = get_object_or_404(Supplier.objects.for_company(company), id=supplier_id)
    purchases = Purchase.objects.for_company(company).filter(supplier=supplier).order_by("-date")
    payments = SupplierPayment.objects.for_company(company).filter(supplier=supplier).order_by("-date")
    total_purchased = purchases.aggregate(t=Sum("total"))["t"] or 0
    total_paid = purchases.aggregate(t=Sum("amount_paid"))["t"] or 0
    return render(request, "webapp/purchases/supplier_detail.html", {
        "supplier": supplier, "purchases": purchases, "payments": payments,
        "total_purchased": total_purchased, "total_paid": total_paid,
        "outstanding": total_purchased - total_paid,
    })


@login_required
@require_feature("webui_suppliers_purchases")
def purchase_list(request):
    company = request.company
    purchases = (
        Purchase.objects.for_company(company).select_related("supplier").order_by("-date")
        if company else []
    )
    return render(request, "webapp/purchases/purchase_list.html", {"purchases": purchases})


@login_required
@require_feature("webui_suppliers_purchases")
@require_permission("purchases.create_purchase")
def purchase_add(request):
    company = request.company
    if request.method == "POST":
        form = PurchaseForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            try:
                purchase_services.create_purchase(
                    company=company, user=request.user, supplier=d["supplier"], date=d["date"],
                    warehouse=d["warehouse"] or _default_warehouse(company), bill_number=d["bill_number"],
                    lines=[{"product": d["product"], "quantity": d["quantity"], "unit_cost": d["unit_cost"]}],
                )
                messages.success(request, "Purchase recorded and stock updated.")
                return redirect("webapp:purchase_list")
            except Exception as exc:
                messages.error(request, f"Couldn't record purchase: {exc}")
    else:
        form = PurchaseForm(company=company, initial={"date": tz.now().date()})

    no_suppliers = not Supplier.objects.for_company(company).filter(is_active=True).exists()
    no_products = not Product.objects.for_company(company).exists()
    return render(request, "webapp/purchases/purchase_form.html", {
        "form": form, "no_suppliers": no_suppliers, "no_products": no_products,
    })


@login_required
@require_permission("purchases.create_purchase")
def supplier_payment_add(request, supplier_id):
    company = request.company
    supplier = get_object_or_404(Supplier.objects.for_company(company), id=supplier_id)
    if request.method == "POST":
        form = SupplierPaymentForm(request.POST, company=company, supplier=supplier)
        if form.is_valid():
            d = form.cleaned_data
            purchase_services.record_supplier_payment(
                company=company, user=request.user, supplier=supplier, amount=d["amount"],
                date=d["date"], purchase=d["purchase"], method=d["method"],
            )
            messages.success(request, "Payment recorded.")
            return redirect("webapp:supplier_detail", supplier_id=supplier.id)
    else:
        form = SupplierPaymentForm(company=company, supplier=supplier, initial={"date": tz.now().date()})
    return render(request, "webapp/purchases/payment_form.html", {"form": form, "supplier": supplier})


@login_required
@require_feature("webui_suppliers_purchases")
def purchase_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    purchases = Purchase.objects.for_company(company)
    total_purchased = purchases.aggregate(t=Sum("total"))["t"] or 0
    total_paid = purchases.aggregate(t=Sum("amount_paid"))["t"] or 0
    by_supplier = (
        purchases.values("supplier__name").annotate(total=Sum("total"), paid=Sum("amount_paid")).order_by("-total")
    )
    context = {
        "total_purchased": total_purchased,
        "total_paid": total_paid,
        "outstanding": total_purchased - total_paid,
        "purchase_count": purchases.count(),
        "by_supplier": by_supplier,
    }
    return render(request, "webapp/purchases/reports.html", context)


# ================= POS (Point of Sale) =================

@login_required
@require_feature("webui_pos")
def pos_view(request):
    import json
    from decimal import Decimal

    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    products = Product.objects.for_company(company).filter(is_active=True).select_related("category")
    is_mobile_shop = company.business_type.code == "mobile_shop"
    product_data = []
    for p in products:
        item_type = (p.attributes or {}).get("item_type", "")
        available_units = []
        if is_mobile_shop and item_type == "handset":
            available_units = list(MobileUnit.objects.for_company(company).filter(
                product=p, status="in_stock"
            ).values("id", "imei", "serial_number", "condition", "warranty_months"))
        product_data.append({
            "id": p.id, "name": p.name, "sku": p.sku, "price": str(p.selling_price),
            "stock": str(len(available_units) if item_type == "handset" else p.current_stock()),
            "size": p.size, "colour": p.colour, "material": p.material, "design": p.design,
            "variant": p.variant_label, "item_type": item_type, "mobile_units": available_units,
            "specs": p.attributes or {},
        })
    customers = Customer.objects.for_company(company).filter(is_active=True).order_by("name")
    branches = Warehouse.objects.for_company(company).filter(is_active=True).order_by("name")

    return render(request, "webapp/pos.html", {
        "products_json": json.dumps(product_data),
        "customers": customers,
        "branches": branches,
        "is_mobile_shop": is_mobile_shop,
    })


@login_required
@require_feature("webui_pos")
@transaction.atomic
def pos_checkout(request):
    import json
    from decimal import Decimal, InvalidOperation
    from django.http import JsonResponse

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    company = request.company
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    cart = payload.get("lines") or []
    if not cart:
        return JsonResponse({"error": "Cart is empty."}, status=400)

    payment_method = payload.get("payment_method", "cash")
    customer_id = payload.get("customer_id")

    if customer_id:
        customer = get_object_or_404(Customer.objects.for_company(company), id=customer_id)
    else:
        customer, _ = Customer.objects.get_or_create(
            company=company, name="Walk-in Customer", defaults={"is_active": True},
        )

    lines = []
    selected_mobile_units = []
    for item in cart:
        product = get_object_or_404(Product.objects.for_company(company), id=item.get("product_id"))
        try:
            quantity = Decimal(str(item.get("quantity", 1)))
            unit_price = Decimal(str(item.get("unit_price")))
        except (InvalidOperation, TypeError):
            return JsonResponse({"error": f"Bad quantity/price for {product.name}."}, status=400)
        if quantity <= 0:
            return JsonResponse({"error": f"Quantity for {product.name} must be positive."}, status=400)
        mobile_unit_id = item.get("mobile_unit_id")
        if mobile_unit_id:
            if quantity != 1:
                return JsonResponse({"error": "Each IMEI handset must be billed as quantity 1."}, status=400)
            unit = get_object_or_404(MobileUnit.objects.select_for_update().for_company(company), id=mobile_unit_id, product=product)
            if unit.status != "in_stock":
                return JsonResponse({"error": f"IMEI {unit.imei} is no longer in stock."}, status=400)
            selected_mobile_units.append(unit)
        lines.append({"product": product, "quantity": quantity, "unit_price": unit_price})

    subtotal = sum((l["quantity"] * l["unit_price"] for l in lines), Decimal("0"))
    coupon_code = (payload.get("coupon_code") or "").strip()
    discount_amount = Decimal("0")
    coupon = None
    if coupon_code:
        try:
            coupon, discount_amount = sales_services.validate_coupon(
                company=company, code=coupon_code, subtotal=subtotal, date=tz.now().date(),
            )
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    try:
        invoice = sales_services.create_invoice(
            company=company, user=request.user, customer=customer, date=tz.now().date(),
            lines=lines, warehouse=_selected_warehouse(company, payload.get("warehouse_id")),
            discount_amount=discount_amount, coupon_code=coupon_code,
        )
        amount_paid = invoice.total
        if payment_method in {"credit", "installment"}:
            if customer.name == "Walk-in Customer":
                raise ValueError("Select a customer for credit or instalment sales.")
            amount_paid = Decimal(str(payload.get("amount_paid") or 0))
            if amount_paid < 0 or amount_paid > invoice.total:
                raise ValueError("Paid amount must be between zero and invoice total.")
        if amount_paid:
            sales_services.record_customer_payment(
                company=company, user=request.user, customer=customer, amount=amount_paid,
                date=tz.now().date(), invoice=invoice,
                method=(payload.get("deposit_method") or "cash") if payment_method in {"credit", "installment"} else payment_method,
            )
        if payment_method in {"credit", "installment"} and customer.credit_limit:
            from apps.collections.services import customer_credit_status
            credit = customer_credit_status(company, customer)
            if credit["over_limit"]:
                raise ValueError(
                    f"Credit limit exceeded. Limit {customer.credit_limit}; outstanding {credit['outstanding']}."
                )
        if payment_method == "installment":
            due_raw = payload.get("next_due_date")
            from django.utils.dateparse import parse_date
            due_date = parse_date(due_raw) if due_raw else tz.now().date() + timedelta(days=30)
            MobileInstallmentPlan.objects.create(
                company=company, invoice=invoice, customer=customer, financed_amount=invoice.total - amount_paid,
                deposit=amount_paid, installment_count=max(1, int(payload.get("installment_count") or 1)),
                frequency=payload.get("frequency") if payload.get("frequency") in {"weekly", "monthly"} else "monthly",
                next_due_date=due_date,
            )
        for unit in selected_mobile_units:
            unit.status = "sold"; unit.buyer = customer; unit.sold_price = next(
                l["unit_price"] for l in lines if l["product"].id == unit.product_id
            ); unit.sold_date = tz.now().date(); unit.sale_invoice = invoice
            unit.warehouse = _selected_warehouse(company, payload.get("warehouse_id"))
            unit.save(update_fields=["status", "buyer", "sold_price", "sold_date", "sale_invoice", "warehouse"])
        if coupon:
            sales_services.redeem_coupon_usage(coupon)

        points_earned = None
        if customer.name != "Walk-in Customer":
            points_earned = customer_services.earn_points(
                company=company, customer=customer, amount_spent=invoice.total,
                date=tz.now().date(), reference=invoice.invoice_number,
            )
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({
        "invoice_id": invoice.id, "invoice_number": invoice.invoice_number, "total": str(invoice.total),
        "discount_amount": str(discount_amount), "points_earned": points_earned,
        "amount_paid": str(amount_paid), "balance": str(invoice.total - amount_paid),
    })


# ================= SALES RETURNS & REFUNDS (shared) =================

@login_required
@require_feature("webui_returns_refunds")
def sales_return_list(request):
    company = request.company
    returns = (
        SalesReturn.objects.for_company(company).select_related("invoice", "invoice__customer").order_by("-date")
        if company else []
    )
    return render(request, "webapp/returns/return_list.html", {"returns": returns})


@login_required
@require_feature("webui_returns_refunds")
def sales_return_lookup(request):
    company = request.company
    invoice = None
    if request.method == "POST":
        form = InvoiceLookupForm(request.POST)
        if form.is_valid():
            invoice = SalesInvoice.objects.for_company(company).filter(
                invoice_number__iexact=form.cleaned_data["invoice_number"].strip()
            ).first()
            if invoice is None:
                messages.error(request, "No invoice found with that number.")
            elif invoice.status == "void":
                messages.error(request, "This invoice has already been fully returned/voided.")
                invoice = None
            else:
                return redirect("webapp:sales_return_add", invoice_id=invoice.id)
    else:
        form = InvoiceLookupForm()
    return render(request, "webapp/returns/lookup.html", {"form": form})


@login_required
@require_feature("webui_returns_refunds")
def sales_return_add(request, invoice_id):
    company = request.company
    invoice = get_object_or_404(
        SalesInvoice.objects.for_company(company).select_related("customer"), id=invoice_id
    )
    lines = SalesInvoiceLine.objects.filter(invoice=invoice).select_related("product")

    already_returned = {}
    for rl in SalesReturnLine.objects.filter(sales_return__invoice=invoice).values("product_id").annotate(q=Sum("quantity")):
        already_returned[rl["product_id"]] = rl["q"]

    for line in lines:
        line.already_returned_qty = already_returned.get(line.product_id, Decimal("0"))
        line.max_returnable = line.quantity - line.already_returned_qty

    if request.method == "POST":
        form = SalesReturnForm(request.POST, initial={"date": tz.now().date()})
        if form.is_valid():
            return_lines = []
            for line in lines:
                qty_str = request.POST.get(f"return_qty_{line.id}", "0")
                try:
                    qty = Decimal(qty_str) if qty_str else Decimal("0")
                except Exception:
                    qty = Decimal("0")
                if qty > 0:
                    max_returnable = line.quantity - already_returned.get(line.product_id, Decimal("0"))
                    if qty > max_returnable:
                        messages.error(request, f"Can't return more than {max_returnable} of {line.product.name}.")
                        return render(request, "webapp/returns/return_form.html", {
                            "form": form, "invoice": invoice, "lines": lines, "already_returned": already_returned,
                        })
                    return_lines.append({"product": line.product, "quantity": qty, "unit_price": line.unit_price})

            if not return_lines:
                messages.error(request, "Enter a quantity to return for at least one item.")
            else:
                try:
                    sales_services.process_return(
                        company=company, user=request.user, invoice=invoice, date=form.cleaned_data["date"],
                        lines=return_lines, warehouse=_default_warehouse(company),
                        reason=form.cleaned_data["reason"], refund_method=form.cleaned_data["refund_method"],
                    )
                    messages.success(request, "Return processed and stock updated.")
                    return redirect("webapp:sales_return_list")
                except Exception as exc:
                    messages.error(request, f"Couldn't process return: {exc}")
    else:
        form = SalesReturnForm(initial={"date": tz.now().date()})

    return render(request, "webapp/returns/return_form.html", {
        "form": form, "invoice": invoice, "lines": lines, "already_returned": already_returned,
    })


@login_required
@require_feature("webui_returns_refunds")
def sales_return_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    returns = SalesReturn.objects.for_company(company)
    context = {
        "total_refunded": returns.aggregate(t=Sum("total"))["t"] or 0,
        "return_count": returns.count(),
        "by_reason": returns.exclude(reason="").values("reason").annotate(count=Count("id")).order_by("-count")[:8],
    }
    return render(request, "webapp/returns/reports.html", context)


# ================= EXPENSES (shared) =================

@login_required
@require_feature("webui_expenses")
def expense_category_list(request):
    company = request.company
    categories = ExpenseCategory.objects.for_company(company).order_by("name") if company else []
    return render(request, "webapp/expenses/category_list.html", {"categories": categories})


@login_required
def expense_category_seed_defaults(request):
    company = request.company
    if request.method == "POST":
        expense_services.seed_default_categories(company)
        messages.success(request, "Common categories (Rent, Salary, Electricity, etc.) added.")
    return redirect("webapp:expense_category_list")


@login_required
@require_permission("expenses.manage")
def expense_category_add(request):
    company = request.company
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Expense category added.")
            return redirect("webapp:expense_category_list")
    else:
        form = ExpenseCategoryForm()
    return render(request, "webapp/expenses/category_form.html", {"form": form})


@login_required
@require_permission("expenses.manage")
def expense_category_delete(request, category_id):
    company = request.company
    obj = get_object_or_404(ExpenseCategory.objects.for_company(company), id=category_id)
    if request.method == "POST":
        try:
            obj.delete()
            messages.success(request, "Category deleted.")
        except ProtectedError:
            messages.error(request, "Can't delete — this category has expenses recorded against it.")
        return redirect("webapp:expense_category_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:expense_category_list", "delete_url": "webapp:expense_category_delete", "delete_id": category_id,
    })


@login_required
@require_feature("webui_expenses")
def expense_list(request):
    company = request.company
    expenses = (
        Expense.objects.for_company(company).select_related("category").order_by("-date")
        if company else []
    )
    total = expenses.aggregate(t=Sum("amount"))["t"] or 0
    return render(request, "webapp/expenses/expense_list.html", {"expenses": expenses, "total": total})


@login_required
@require_feature("webui_expenses")
@require_permission("expenses.manage")
def expense_add(request):
    company = request.company
    if request.method == "POST":
        form = ExpenseForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            expense_services.record_expense(
                company=company, user=request.user, category=d["category"], date=d["date"],
                amount=d["amount"], description=d["description"], payment_method=d["payment_method"],
            )
            messages.success(request, "Expense recorded.")
            return redirect("webapp:expense_list")
    else:
        form = ExpenseForm(company=company, initial={"date": tz.now().date()})

    no_categories = not ExpenseCategory.objects.for_company(company).exists()
    return render(request, "webapp/expenses/expense_form.html", {"form": form, "no_categories": no_categories})


@login_required
@require_feature("webui_expenses")
def expense_reports(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    expenses = Expense.objects.for_company(company)
    context = {
        "total": expenses.aggregate(t=Sum("amount"))["t"] or 0,
        "by_category": (
            expenses.values("category__name").annotate(total=Sum("amount"), count=Count("id")).order_by("-total")
        ),
    }
    return render(request, "webapp/expenses/reports.html", context)


# ================= STAFF & ROLES (RBAC) =================

@login_required
@require_feature("webui_team_roles")
@require_permission("tenants.manage_members")
def staff_members_list(request):
    company = request.company
    memberships = (
        CompanyMembership.objects.filter(company=company, is_active=True)
        .select_related("user", "role").order_by("user__username")
    )
    return render(request, "webapp/rbac/members_list.html", {"memberships": memberships})


@login_required
@require_feature("webui_team_roles")
@require_permission("tenants.manage_members")
def staff_invite(request):
    company = request.company
    if request.method == "POST":
        form = InviteStaffForm(request.POST, company=company)
        if form.is_valid():
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.create_user(
                    username=form.cleaned_data["username"], email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                )
                tenant_services.invite_member(company=company, user=user, role=form.cleaned_data["role"])
                messages.success(request, f"{user.username} added as {form.cleaned_data['role'].name}.")
                return redirect("webapp:staff_members_list")
            except Exception as exc:
                messages.error(request, f"Couldn't add staff member: {exc}")
    else:
        form = InviteStaffForm(company=company)
    return render(request, "webapp/rbac/invite_staff.html", {"form": form})


@login_required
@require_permission("tenants.manage_members")
def staff_role_change(request, membership_id):
    company = request.company
    membership = get_object_or_404(CompanyMembership.objects.filter(company=company), id=membership_id)
    if request.method == "POST":
        form = ChangeMemberRoleForm(request.POST, company=company)
        if form.is_valid():
            membership.role = form.cleaned_data["role"]
            membership.save(update_fields=["role"])
            messages.success(request, "Role updated.")
            return redirect("webapp:staff_members_list")
    else:
        form = ChangeMemberRoleForm(company=company, initial={"role": membership.role_id})
    return render(request, "webapp/rbac/change_role.html", {"form": form, "membership": membership})


@login_required
@require_permission("tenants.manage_members")
def staff_remove(request, membership_id):
    company = request.company
    membership = get_object_or_404(CompanyMembership.objects.filter(company=company), id=membership_id)
    if membership.user_id == request.user.id:
        messages.error(request, "You can't remove yourself.")
        return redirect("webapp:staff_members_list")
    if request.method == "POST":
        membership.is_active = False
        membership.save(update_fields=["is_active"])
        messages.success(request, "Removed from this business.")
        return redirect("webapp:staff_members_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": membership, "cancel_url": "webapp:staff_members_list",
        "delete_url": "webapp:staff_remove", "delete_id": membership_id,
    })


@login_required
@require_feature("webui_team_roles")
@require_permission("tenants.manage_roles")
def role_list(request):
    company = request.company
    roles = Role.objects.filter(company=company).prefetch_related("permissions__permission").order_by("name")
    return render(request, "webapp/rbac/role_list.html", {"roles": roles})


@login_required
@require_feature("webui_team_roles")
@require_permission("tenants.manage_roles")
def role_add(request):
    company = request.company
    if request.method == "POST":
        form = CustomRoleForm(request.POST)
        if form.is_valid():
            Role.objects.create(company=company, name=form.cleaned_data["name"], is_system_role=False)
            messages.success(request, "Role created — set its permissions next.")
            return redirect("webapp:role_list")
    else:
        form = CustomRoleForm()
    return render(request, "webapp/rbac/role_form.html", {"form": form})


@login_required
@require_feature("webui_team_roles")
@require_permission("tenants.manage_roles")
def role_permissions_edit(request, role_id):
    company = request.company
    role = get_object_or_404(Role.objects.filter(company=company), id=role_id)
    if role.is_system_role:
        messages.error(request, "System roles (Owner/Accountant/Staff) can't be edited — create a custom role instead.")
        return redirect("webapp:role_list")

    all_permissions = Permission.objects.all().order_by("module", "code")
    current_codes = set(role.permissions.values_list("permission__code", flat=True))

    if request.method == "POST":
        selected = request.POST.getlist("permissions")
        tenant_services.set_role_permissions(role=role, permission_codes=selected)
        messages.success(request, "Permissions updated.")
        return redirect("webapp:role_list")

    return render(request, "webapp/rbac/role_permissions.html", {
        "role": role, "all_permissions": all_permissions, "current_codes": current_codes,
    })


# ================= ANALYTICS (charts, shared) =================

@login_required
@require_feature("webui_analytics")
def analytics_view(request):
    import json

    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    period = request.GET.get("period", "this_month")
    today = tz.now().date()

    if period == "today":
        start, end = today, today
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
    elif period == "this_week":
        start = today - timedelta(days=today.weekday())
        end = today
    elif period == "last_month":
        first_of_this_month = today.replace(day=1)
        end = first_of_this_month - timedelta(days=1)
        start = end.replace(day=1)
    elif period == "this_year":
        start = today.replace(month=1, day=1)
        end = today
    elif period == "custom":
        try:
            start = tz.datetime.strptime(request.GET.get("start", ""), "%Y-%m-%d").date()
            end = tz.datetime.strptime(request.GET.get("end", ""), "%Y-%m-%d").date()
        except ValueError:
            start, end = today.replace(day=1), today
    else:  # this_month
        start, end = today.replace(day=1), today

    invoices = SalesInvoice.objects.for_company(company).filter(date__gte=start, date__lte=end).exclude(status="void")
    expenses = Expense.objects.for_company(company).filter(date__gte=start, date__lte=end)

    total_sales = invoices.aggregate(t=Sum("total"))["t"] or 0
    total_expenses = expenses.aggregate(t=Sum("amount"))["t"] or 0

    sales_by_day = (
        invoices.values("date").annotate(total=Sum("total")).order_by("date")
    )
    chart_labels = [row["date"].strftime("%d %b") for row in sales_by_day]
    chart_values = [float(row["total"]) for row in sales_by_day]

    top_products = (
        SalesInvoiceLine.objects.filter(invoice__company=company, invoice__date__gte=start, invoice__date__lte=end)
        .exclude(invoice__status="void")
        .values("product__name").annotate(revenue=Sum("line_total")).order_by("-revenue")[:8]
    )
    product_labels = [row["product__name"] for row in top_products]
    product_values = [float(row["revenue"]) for row in top_products]

    from apps.sales.models import CustomerPayment as CP
    by_method = (
        CP.objects.for_company(company).filter(date__gte=start, date__lte=end)
        .values("method").annotate(total=Sum("amount")).order_by("-total")
    )
    method_labels = [row["method"].title() for row in by_method]
    method_values = [float(row["total"]) for row in by_method]

    context = {
        "period": period, "start": start, "end": end,
        "periods": [
            ("today", "Today"), ("yesterday", "Yesterday"), ("this_week", "This Week"),
            ("this_month", "This Month"), ("last_month", "Last Month"), ("this_year", "This Year"),
        ],
        "total_sales": total_sales, "total_expenses": total_expenses,
        "net_profit": total_sales - total_expenses,
        "invoice_count": invoices.count(),
        "chart_labels": json.dumps(chart_labels),
        "chart_values": json.dumps(chart_values),
        "product_labels": json.dumps(product_labels),
        "product_values": json.dumps(product_values),
        "method_labels": json.dumps(method_labels),
        "method_values": json.dumps(method_values),
    }
    return render(request, "webapp/analytics.html", context)


# ================= COUPONS =================

@login_required
@require_feature("webui_coupons_loyalty")
def coupon_list(request):
    company = request.company
    coupons = Coupon.objects.for_company(company).order_by("-id") if company else []
    return render(request, "webapp/coupons/coupon_list.html", {"coupons": coupons})


@login_required
@require_feature("webui_coupons_loyalty")
def coupon_add(request):
    company = request.company
    if request.method == "POST":
        form = CouponForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Coupon created.")
            return redirect("webapp:coupon_list")
    else:
        form = CouponForm(initial={"start_date": tz.now().date()})
    return render(request, "webapp/coupons/coupon_form.html", {"form": form})


@login_required
@require_feature("webui_coupons_loyalty")
def coupon_toggle(request, coupon_id):
    company = request.company
    coupon = get_object_or_404(Coupon.objects.for_company(company), id=coupon_id)
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=["is_active"])
    messages.success(request, f"Coupon {'activated' if coupon.is_active else 'deactivated'}.")
    return redirect("webapp:coupon_list")


@login_required
def coupon_validate_api(request):
    """Called from POS via fetch to preview a coupon's discount before checkout."""
    from django.http import JsonResponse
    company = request.company
    code = request.GET.get("code", "")
    subtotal = request.GET.get("subtotal", "0")
    try:
        coupon, discount = sales_services.validate_coupon(
            company=company, code=code, subtotal=Decimal(subtotal), date=tz.now().date(),
        )
        return JsonResponse({"valid": True, "discount": str(discount)})
    except Exception as exc:
        return JsonResponse({"valid": False, "error": str(exc)})


# ================= LOYALTY =================

@login_required
@require_feature("webui_coupons_loyalty")
def loyalty_accounts_list(request):
    company = request.company
    accounts = (
        LoyaltyAccount.objects.for_company(company).select_related("customer").order_by("-points_balance")
        if company else []
    )
    return render(request, "webapp/coupons/loyalty_list.html", {"accounts": accounts})


@login_required
@require_feature("webui_coupons_loyalty")
def loyalty_redeem(request):
    company = request.company
    if request.method == "POST":
        form = RedeemPointsForm(request.POST, company=company)
        if form.is_valid():
            try:
                customer_services.redeem_points(
                    company=company, customer=form.cleaned_data["customer"], points=form.cleaned_data["points"],
                    date=tz.now().date(), reference=form.cleaned_data["reason"],
                )
                messages.success(request, "Points redeemed.")
                return redirect("webapp:loyalty_accounts_list")
            except Exception as exc:
                messages.error(request, str(exc))
    else:
        form = RedeemPointsForm(company=company)
    return render(request, "webapp/coupons/loyalty_redeem.html", {"form": form})


# ================= SETTINGS =================

@login_required
@require_permission("tenants.manage_roles")
def company_settings(request):
    company = request.company
    if request.method == "POST":
        form = CompanySettingsForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Business settings updated.")
            return redirect("webapp:company_settings")
    else:
        form = CompanySettingsForm(instance=company)
    return render(request, "webapp/settings.html", {"form": form})


# ================= NOTIFICATIONS =================

@login_required
def notification_list(request):
    company = request.company
    notification_services.check_low_stock_and_notify(company)
    notification_services.check_overdue_invoices_and_notify(company)
    from apps.inventory.services import check_batch_expiry_and_notify
    check_batch_expiry_and_notify(company)

    notifications = Notification.objects.filter(company=company).filter(
        Q(recipient=request.user) | Q(recipient__isnull=True)
    ).order_by("-created_at")[:100]
    return render(request, "webapp/notifications.html", {"notifications": notifications})


@login_required
def notification_mark_read(request, notification_id):
    company = request.company
    notif = get_object_or_404(Notification.objects.filter(company=company), id=notification_id)
    notif.is_read = True
    notif.save(update_fields=["is_read"])
    return redirect("webapp:notification_list")


@login_required
def notification_mark_all_read(request):
    company = request.company
    Notification.objects.filter(company=company).filter(
        Q(recipient=request.user) | Q(recipient__isnull=True)
    ).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect("webapp:notification_list")


# ================= BRANCHES (multi-branch support) =================

@login_required
@require_feature("webui_branches")
@require_permission("tenants.manage_roles")
def branch_list(request):
    company = request.company
    _default_warehouse(company)
    branches = Warehouse.objects.for_company(company).filter(is_active=True).order_by("name")
    return render(request, "webapp/branches/branch_list.html", {"branches": branches})


@login_required
@require_feature("webui_branches")
@require_permission("tenants.manage_roles")
def branch_add(request):
    company = request.company
    if request.method == "POST":
        form = BranchForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            if obj.is_default:
                Warehouse.objects.for_company(company).update(is_default=False)
            obj.save()
            messages.success(request, "Branch added.")
            return redirect("webapp:branch_list")
    else:
        form = BranchForm()
    return render(request, "webapp/branches/branch_form.html", {"form": form})


@login_required
@require_feature("webui_branches")
@require_permission("tenants.manage_roles")
def branch_edit(request, branch_id):
    company = request.company
    obj = get_object_or_404(Warehouse.objects.for_company(company), id=branch_id)
    if request.method == "POST":
        form = BranchForm(request.POST, instance=obj)
        if form.is_valid():
            branch = form.save(commit=False)
            if branch.is_default:
                Warehouse.objects.for_company(company).exclude(id=branch.id).update(is_default=False)
            branch.save()
            messages.success(request, "Branch updated.")
            return redirect("webapp:branch_list")
    else:
        form = BranchForm(instance=obj)
    return render(request, "webapp/branches/branch_form.html", {"form": form, "editing": True})


@login_required
@require_permission("tenants.manage_roles")
def branch_delete(request, branch_id):
    company = request.company
    obj = get_object_or_404(Warehouse.objects.for_company(company), id=branch_id)
    if request.method == "POST":
        if Warehouse.objects.for_company(company).filter(is_active=True).count() <= 1:
            messages.error(request, "Can't delete your only branch.")
            return redirect("webapp:branch_list")
        try:
            obj.is_active = False
            obj.save(update_fields=["is_active"])
            messages.success(request, "Branch removed.")
        except ProtectedError:
            messages.error(request, "Can't delete — this branch has records linked to it.")
        return redirect("webapp:branch_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": obj, "cancel_url": "webapp:branch_list", "delete_url": "webapp:branch_delete", "delete_id": branch_id,
    })


@login_required
@require_feature("webui_branches")
def branch_stock_report(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    branches = list(Warehouse.objects.for_company(company).filter(is_active=True).order_by("name"))
    products = (
        Product.objects.for_company(company).filter(is_active=True)
        .annotate(variant_count=Count("variants")).filter(variant_count=0)
        .order_by("name", "colour", "size")
    )

    rows = []
    for product in products:
        rows.append({
            "product": product,
            "stock_by_branch": [product.current_stock(warehouse=b) for b in branches],
            "total": product.current_stock(),
        })

    return render(request, "webapp/branches/stock_report.html", {"branches": branches, "rows": rows})


# ================= IMPORT / EXPORT =================

@login_required
def product_export_csv(request):
    import csv
    import json
    from django.http import HttpResponse

    company = request.company
    products = Product.objects.for_company(company).select_related("category", "brand", "unit").order_by("name")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="products.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "SKU", "Name", "Category", "Brand", "Unit", "Cost Price", "Selling Price",
        "Reorder Level", "Size", "Colour", "Material", "Design", "Attributes JSON", "Current Stock",
    ])
    for p in products:
        writer.writerow([
            p.sku, p.name, p.category.name if p.category else "", p.brand.name if p.brand else "",
            p.unit.name, p.cost_price, p.selling_price, p.reorder_level,
            p.size, p.colour, p.material, p.design, json.dumps(p.attributes or {}, default=str), p.current_stock(),
        ])
    return response


@login_required
def product_import_csv(request):
    import csv
    import io
    import json

    company = request.company
    if request.method == "POST":
        form = ProductImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES["csv_file"]
            try:
                decoded = csv_file.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                messages.error(request, "Couldn't read that file — please upload a plain CSV.")
                return render(request, "webapp/import_export/product_import.html", {"form": form})

            reader = csv.DictReader(io.StringIO(decoded))
            required = {"SKU", "Name", "Unit", "Selling Price"}
            if not required.issubset(set(reader.fieldnames or [])):
                messages.error(
                    request,
                    f"CSV must have these columns: {', '.join(sorted(required))}. "
                    f"(Optional: Category, Brand, Cost Price, Reorder Level)",
                )
                return render(request, "webapp/import_export/product_import.html", {"form": form})

            created, updated, errors = 0, 0, []
            default_unit = None
            for i, row in enumerate(reader, start=2):
                sku = (row.get("SKU") or "").strip()
                name = (row.get("Name") or "").strip()
                unit_name = (row.get("Unit") or "").strip()
                if not sku or not name or not unit_name:
                    errors.append(f"Row {i}: SKU, Name and Unit are required.")
                    continue
                try:
                    selling_price = Decimal(row.get("Selling Price") or "0")
                    cost_price = Decimal(row.get("Cost Price") or "0")
                    reorder_level = int(row.get("Reorder Level") or 0)
                except Exception:
                    errors.append(f"Row {i}: invalid number in price/reorder level.")
                    continue

                unit, _ = Unit.objects.get_or_create(company=company, name=unit_name)
                category = None
                if row.get("Category", "").strip():
                    category, _ = ProductCategory.objects.get_or_create(company=company, name=row["Category"].strip())
                brand = None
                if row.get("Brand", "").strip():
                    brand, _ = Brand.objects.get_or_create(company=company, name=row["Brand"].strip())
                try:
                    attributes = json.loads(row.get("Attributes JSON") or "{}")
                    if not isinstance(attributes, dict):
                        raise ValueError
                except (json.JSONDecodeError, ValueError):
                    errors.append(f"Row {i}: Attributes JSON must be a JSON object.")
                    continue

                obj, was_created = Product.objects.update_or_create(
                    company=company, sku=sku,
                    defaults={
                        "name": name, "unit": unit, "category": category, "brand": brand,
                        "cost_price": cost_price, "selling_price": selling_price, "reorder_level": reorder_level,
                        "size": (row.get("Size") or "").strip(),
                        "colour": (row.get("Colour") or "").strip(),
                        "material": (row.get("Material") or "").strip(),
                        "design": (row.get("Design") or "").strip(),
                        "attributes": attributes,
                    },
                )
                created += int(was_created)
                updated += int(not was_created)

            if errors:
                messages.warning(request, f"Imported {created} new, updated {updated}. {len(errors)} row(s) skipped: " + " | ".join(errors[:5]))
            else:
                messages.success(request, f"Imported {created} new products, updated {updated} existing.")
            return redirect("webapp:product_list")
    else:
        form = ProductImportForm()
    return render(request, "webapp/import_export/product_import.html", {"form": form})


@login_required
def customer_export_csv(request):
    import csv
    from django.http import HttpResponse

    company = request.company
    customers = Customer.objects.for_company(company).order_by("name")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="customers.csv"'
    writer = csv.writer(response)
    writer.writerow(["Name", "Phone", "Email", "Address"])
    for c in customers:
        writer.writerow([c.name, c.phone, c.email, c.address])
    return response


@login_required
def sales_export_csv(request):
    import csv
    from django.http import HttpResponse

    company = request.company
    invoices = SalesInvoice.objects.for_company(company).select_related("customer").order_by("-date")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="sales.csv"'
    writer = csv.writer(response)
    writer.writerow(["Invoice #", "Date", "Customer", "Subtotal", "Discount", "Tax", "Total", "Paid", "Status"])
    for inv in invoices:
        writer.writerow([
            inv.invoice_number, inv.date, inv.customer.name, inv.subtotal, inv.discount_amount,
            inv.tax_amount, inv.total, inv.amount_paid, inv.get_status_display(),
        ])
    return response


# ================= PLATFORM ADMIN PORTAL =================

def superuser_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not (request.user.is_active and request.user.is_platform_admin):
            messages.error(request, "Only a platform admin can access that.")
            return redirect("webapp:dashboard")
        return view_func(request, *args, **kwargs)
    return wrapped


@login_required
@superuser_required
def platform_admin_dashboard(request):
    companies = Company.objects.filter(is_active=True)
    total_clients = companies.count()
    subs = Subscription.objects.select_related("plan", "company")

    total_revenue = SubscriptionPayment.objects.aggregate(t=Sum("amount"))["t"] or 0
    active_count = subs.filter(status="active").count()
    trial_count = subs.filter(status="trial").count()
    expired_count = subs.filter(status__in=["expired", "cancelled"]).count()

    recent_companies = companies.select_related("business_type").order_by("-created_at")[:8]
    recent_payments = SubscriptionPayment.objects.select_related("subscription__company").order_by("-paid_on")[:8]

    context = {
        "total_clients": total_clients,
        "total_revenue": total_revenue,
        "active_count": active_count,
        "trial_count": trial_count,
        "expired_count": expired_count,
        "recent_companies": recent_companies,
        "recent_payments": recent_payments,
        "business_type_count": BusinessType.objects.count(),
        "module_count": Module.objects.count(),
        "multi_business_count": Company.objects.filter(business_suites__is_active=True).annotate(suite_count=Count("business_suites")).filter(suite_count__gt=1).distinct().count(),
    }
    return render(request, "webapp/platform_admin/dashboard.html", context)


@login_required
@superuser_required
def platform_admin_company_list(request):
    companies = (
        Company.objects.all().select_related("business_type", "subscription", "subscription__plan")
        .order_by("-created_at")
    )
    return render(request, "webapp/platform_admin/company_list.html", {"companies": companies})


@login_required
@superuser_required
def platform_admin_company_detail(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    memberships = CompanyMembership.objects.filter(company=company, is_active=True).select_related("user", "role")
    owner_membership = memberships.filter(role__name="Owner").first()
    subscription = Subscription.objects.filter(company=company).select_related("plan").first()
    payments = SubscriptionPayment.objects.filter(subscription__company=company).order_by("-paid_on") if subscription else []

    from apps.sales.models import SalesInvoice
    revenue = SalesInvoice.objects.for_company(company).exclude(status="void").aggregate(t=Sum("total"))["t"] or 0
    customer_count = Customer.objects.for_company(company).count()
    active_modules = list(company.active_modules().values_list("name", flat=True))

    return render(request, "webapp/platform_admin/company_detail.html", {
        "company": company, "memberships": memberships, "owner_membership": owner_membership,
        "subscription": subscription, "payments": payments,
        "revenue": revenue, "customer_count": customer_count, "active_modules": active_modules,
        "business_suites": company.business_suites.filter(is_active=True).select_related("business_type"),
    })


@login_required
@superuser_required
def platform_admin_edit_user(request, user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    if user_obj.is_platform_admin and user_obj.pk != request.user.pk:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Platform administrator credentials must be managed by their owner.")

    if request.method == "POST":
        form = EditUserCredentialsForm(request.POST, user_instance=user_obj)
        if form.is_valid():
            user_obj.username = form.cleaned_data["username"]
            user_obj.email = form.cleaned_data["email"]
            if form.cleaned_data["new_password"]:
                user_obj.set_password(form.cleaned_data["new_password"])
            user_obj.save()
            messages.success(request, f"Updated login for {user_obj.username}.")
            membership = CompanyMembership.objects.filter(user=user_obj, is_active=True).first()
            if membership:
                return redirect("webapp:platform_admin_company_detail", company_id=membership.company_id)
            return redirect("webapp:platform_admin_company_list")
    else:
        form = EditUserCredentialsForm(initial={"username": user_obj.username, "email": user_obj.email}, user_instance=user_obj)

    return render(request, "webapp/platform_admin/edit_user.html", {"form": form, "user_obj": user_obj})


# ================= PLATFORM ADMIN: PRICING PLANS =================

@login_required
@superuser_required
def platform_plan_list(request):
    plans = SubscriptionPlan.objects.all().order_by("country", "price")
    return render(request, "webapp/platform_admin/plan_list.html", {"plans": plans})


@login_required
@superuser_required
def platform_plan_add(request):
    if request.method == "POST":
        form = SubscriptionPlanForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Plan added.")
            return redirect("webapp:platform_plan_list")
    else:
        form = SubscriptionPlanForm()
    return render(request, "webapp/platform_admin/plan_form.html", {"form": form})


@login_required
@superuser_required
def platform_plan_edit(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    if request.method == "POST":
        form = SubscriptionPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, "Plan updated.")
            return redirect("webapp:platform_plan_list")
    else:
        form = SubscriptionPlanForm(instance=plan)
    return render(request, "webapp/platform_admin/plan_form.html", {"form": form, "editing": True})


# ================= PLATFORM ADMIN: CLIENT LIFECYCLE =================

@login_required
@superuser_required
def platform_admin_company_delete(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == "POST":
        company.is_active = False
        company.archived_at = tz.now()
        company.save(update_fields=["is_active", "archived_at"])
        messages.success(request, f"{company.name} archived. You can restore it from the client list.")
        return redirect("webapp:platform_admin_company_list")
    return render(request, "webapp/confirm_delete.html", {
        "object": company, "cancel_url": "webapp:platform_admin_company_list",
        "delete_url": "webapp:platform_admin_company_delete", "delete_id": company_id,
    })


@login_required
@superuser_required
def platform_admin_change_plan(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    subscription = Subscription.objects.filter(company=company).first()

    if request.method == "POST":
        plan_id = request.POST.get("plan")
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)
        if subscription:
            subscription.plan = plan
            subscription.save(update_fields=["plan"])
        else:
            from apps.subscriptions.services import start_trial_subscription
            start_trial_subscription(company, plan=plan)
        messages.success(request, f"Plan set to {plan.name} ({plan.country}).")
        return redirect("webapp:platform_admin_company_detail", company_id=company.id)

    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("country", "price")
    return render(request, "webapp/platform_admin/change_plan.html", {
        "company": company, "subscription": subscription, "plans": plans,
    })


@login_required
@superuser_required
def platform_admin_record_payment(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    subscription = get_object_or_404(Subscription, company=company)

    if request.method == "POST":
        amount = request.POST.get("amount")
        method = request.POST.get("method", "manual")
        reference = request.POST.get("reference", "")
        try:
            from apps.subscriptions.services import renew_subscription
            new_end = tz.now().date() + timedelta(days=365 if subscription.plan.billing_period == "yearly" else 30)
            renew_subscription(subscription, new_end_date=new_end, amount=Decimal(amount), method=method, reference=reference)
            messages.success(request, "Payment recorded and subscription renewed.")
        except Exception as exc:
            messages.error(request, f"Couldn't record payment: {exc}")
        return redirect("webapp:platform_admin_company_detail", company_id=company.id)

    return render(request, "webapp/platform_admin/record_payment.html", {"company": company, "subscription": subscription})


# ================= PLATFORM ADMIN: ANALYTICS =================

@login_required
@superuser_required
def platform_admin_analytics(request):
    import json

    companies = Company.objects.filter(is_active=True)
    payments = SubscriptionPayment.objects.select_related("subscription__company")

    by_country = (
        companies.exclude(country="").values("country").annotate(count=Count("id")).order_by("-count")
    )
    country_labels = [row["country"] for row in by_country]
    country_values = [row["count"] for row in by_country]

    by_plan = (
        Subscription.objects.filter(company__is_active=True).values("plan__name", "plan__country")
        .annotate(count=Count("id")).order_by("-count")
    )
    plan_labels = [f'{row["plan__name"]} ({row["plan__country"]})' for row in by_plan]
    plan_values = [row["count"] for row in by_plan]

    # group revenue by (year, month) in Python — avoids DB-specific TruncMonth quirks (seen earlier with SQLite)
    monthly = {}
    for p in payments:
        key = p.paid_on.strftime("%Y-%m")
        monthly[key] = monthly.get(key, Decimal("0")) + p.amount
    months_sorted = sorted(monthly.keys())[-12:]
    revenue_labels = months_sorted
    revenue_values = [float(monthly[m]) for m in months_sorted]

    context = {
        "total_revenue": payments.aggregate(t=Sum("amount"))["t"] or 0,
        "total_clients": companies.count(),
        "country_labels": json.dumps(country_labels),
        "country_values": json.dumps(country_values),
        "plan_labels": json.dumps(plan_labels),
        "plan_values": json.dumps(plan_values),
        "revenue_labels": json.dumps(revenue_labels),
        "revenue_values": json.dumps(revenue_values),
    }
    return render(request, "webapp/platform_admin/analytics.html", context)


# ================= BILLING (client self-service) =================

@login_required
def billing_view(request):
    company = request.company
    if company is None:
        return render(request, "webapp/no_company.html")

    subscription = Subscription.objects.filter(company=company).select_related("plan").first()
    is_owner = getattr(request.role, "name", None) == "Owner"
    days_left = subscription.days_remaining() if subscription else None
    is_expired = subscription and days_left is not None and days_left < 0
    payments = SubscriptionPayment.objects.filter(subscription=subscription).order_by("-paid_on") if subscription else []

    if request.GET.get("stripe_success"):
        messages.success(request, "Payment received — your subscription will update within a few seconds.")
    elif request.GET.get("stripe_cancelled"):
        messages.error(request, "Checkout was cancelled — no charge was made.")

    if request.method == "POST":
        if not is_owner:
            messages.error(request, "Only the business owner can submit a payment.")
            return redirect("webapp:billing")
        form = BillingPaymentForm(request.POST)
        if form.is_valid() and subscription:
            subscription_services.submit_client_payment(
                subscription, amount=form.cleaned_data["amount"], method=form.cleaned_data["method"],
                reference=form.cleaned_data["reference"], notes=form.cleaned_data["notes"],
            )
            messages.success(request, "Payment submitted — a platform admin will confirm it shortly.")
            return redirect("webapp:billing")
    else:
        form = BillingPaymentForm(initial={"amount": subscription.plan.price if subscription else None})

    gateway = get_payment_gateway_config()
    return render(request, "webapp/billing.html", {
        "subscription": subscription, "is_owner": is_owner, "days_left": days_left,
        "is_expired": is_expired, "payments": payments, "form": form,
        "is_gcc": _is_gcc_country(company.country),
        "is_india": (company.country or "").strip() == "India",
        "stripe_configured": gateway.stripe_enabled,
        "razorpay_configured": gateway.razorpay_enabled,
        "razorpay_key_id": gateway.razorpay_key_id,
    })


# ================= PLATFORM ADMIN: PENDING PAYMENTS =================

@login_required
@superuser_required
def platform_pending_payments(request):
    pending = (
        SubscriptionPayment.objects.filter(is_confirmed=False)
        .select_related("subscription__company", "subscription__plan").order_by("paid_on")
    )
    return render(request, "webapp/platform_admin/pending_payments.html", {"pending": pending})


@login_required
@superuser_required
def platform_approve_payment(request, payment_id):
    payment = get_object_or_404(SubscriptionPayment, id=payment_id)
    if request.method == "POST":
        subscription_services.approve_client_payment(payment)
        messages.success(request, f"Payment approved — {payment.subscription.company.name}'s subscription renewed.")
    return redirect("webapp:platform_pending_payments")


# ================= BILLING: STRIPE (international / non-GCC) =================

def _is_gcc_country(country):
    return (country or "").strip() in settings.GCC_COUNTRIES


@login_required
def billing_stripe_checkout(request):
    import stripe

    company = request.company
    if company is None or _is_gcc_country(company.country):
        messages.error(request, "Card payment isn't set up for your country — use bank transfer below.")
        return redirect("webapp:billing")

    gateway = get_payment_gateway_config()
    if not gateway.stripe_enabled:
        messages.error(request, "Card payments aren't configured yet. Please use bank transfer for now.")
        return redirect("webapp:billing")

    subscription = Subscription.objects.filter(company=company).select_related("plan").first()
    if subscription is None:
        messages.error(request, "No subscription found.")
        return redirect("webapp:billing")

    is_owner = getattr(request.role, "name", None) == "Owner"
    if not is_owner:
        messages.error(request, "Only the business owner can pay.")
        return redirect("webapp:billing")

    stripe.api_key = gateway.stripe_secret_key
    plan = subscription.plan
    success_url = request.build_absolute_uri(reverse("webapp:billing")) + "?stripe_success=1"
    cancel_url = request.build_absolute_uri(reverse("webapp:billing")) + "?stripe_cancelled=1"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": plan.currency.lower(),
                    "product_data": {"name": f"{plan.name} — {company.name}"},
                    "unit_amount": int(plan.price * 100),
                },
                "quantity": 1,
            }],
            metadata={"subscription_id": str(subscription.id)},
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except Exception as exc:
        messages.error(request, f"Couldn't start checkout: {exc}")
        return redirect("webapp:billing")

    return redirect(session.url)


@csrf_exempt
def billing_stripe_webhook(request):
    import stripe

    gateway = get_payment_gateway_config()
    if not gateway.stripe_enabled or not gateway.stripe_webhook_secret:
        return HttpResponse(status=400)

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, gateway.stripe_webhook_secret)
    except Exception:
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        subscription_id = session.get("metadata", {}).get("subscription_id")
        amount_total = session.get("amount_total") or 0
        if subscription_id:
            subscription = Subscription.objects.filter(id=subscription_id).select_related("plan").first()
            if subscription:
                subscription_services.confirm_stripe_payment(
                    subscription, amount=Decimal(amount_total) / 100, reference=session.get("id", ""),
                )

    return HttpResponse(status=200)


# ================= BILLING: RAZORPAY (India — UPI / PhonePe / cards) =================

@login_required
def billing_razorpay_order(request):
    import razorpay
    from django.http import JsonResponse

    company = request.company
    if company is None or (company.country or "").strip() != "India":
        return JsonResponse({"error": "Razorpay is only available for India."}, status=400)

    gateway = get_payment_gateway_config()
    if not gateway.razorpay_enabled:
        return JsonResponse({"error": "Card/UPI payment isn't configured yet."}, status=400)

    is_owner = getattr(request.role, "name", None) == "Owner"
    if not is_owner:
        return JsonResponse({"error": "Only the business owner can pay."}, status=403)

    subscription = Subscription.objects.filter(company=company).select_related("plan").first()
    if subscription is None:
        return JsonResponse({"error": "No subscription found."}, status=400)

    client = razorpay.Client(auth=(gateway.razorpay_key_id, gateway.razorpay_key_secret))
    amount_paise = int(subscription.plan.price * 100)
    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": subscription.plan.currency,
            "receipt": f"sub-{subscription.id}",
            "notes": {"subscription_id": str(subscription.id), "company": company.name},
        })
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse({
        "order_id": order["id"], "amount": amount_paise, "currency": subscription.plan.currency,
        "key_id": gateway.razorpay_key_id, "company_name": company.name, "plan_name": subscription.plan.name,
    })


@login_required
@csrf_exempt
def billing_razorpay_verify(request):
    import razorpay
    from django.http import JsonResponse

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    company = request.company
    subscription = Subscription.objects.filter(company=company).select_related("plan").first() if company else None
    if subscription is None:
        return JsonResponse({"error": "No subscription found."}, status=400)

    payment_id = request.POST.get("razorpay_payment_id")
    order_id = request.POST.get("razorpay_order_id")
    signature = request.POST.get("razorpay_signature")

    gateway = get_payment_gateway_config()
    if not gateway.razorpay_enabled:
        return JsonResponse({"error": "Card/UPI payment isn't configured yet."}, status=400)
    client = razorpay.Client(auth=(gateway.razorpay_key_id, gateway.razorpay_key_secret))
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({"error": "Payment verification failed."}, status=400)

    subscription_services.confirm_razorpay_payment(
        subscription, amount=subscription.plan.price, reference=payment_id,
    )
    return JsonResponse({"success": True})


@csrf_exempt
def billing_razorpay_webhook(request):
    import razorpay

    gateway = get_payment_gateway_config()
    if not gateway.razorpay_enabled or not gateway.razorpay_webhook_secret:
        return HttpResponse(status=400)

    client = razorpay.Client(auth=(gateway.razorpay_key_id, gateway.razorpay_key_secret))
    try:
        client.utility.verify_webhook_signature(
            request.body.decode(), request.META.get("HTTP_X_RAZORPAY_SIGNATURE", ""), gateway.razorpay_webhook_secret,
        )
    except Exception:
        return HttpResponse(status=400)

    import json
    event = json.loads(request.body)
    if event.get("event") == "payment.captured":
        payment = event["payload"]["payment"]["entity"]
        notes = payment.get("notes", {})
        subscription_id = notes.get("subscription_id")
        if subscription_id:
            subscription = Subscription.objects.filter(id=subscription_id).select_related("plan").first()
            if subscription:
                # idempotent-ish: only act if the subscription isn't already renewed past today by this exact payment id
                already = SubscriptionPayment.objects.filter(reference=payment["id"]).exists()
                if not already:
                    subscription_services.confirm_razorpay_payment(
                        subscription, amount=Decimal(payment["amount"]) / 100, reference=payment["id"],
                    )

    return HttpResponse(status=200)


@login_required
@superuser_required
def platform_admin_manage_modules(request, company_id):
    """Platform-admin feature centre for a tenant.

    Unlike the original screen (which only exposed WEB_FEATURES), this lists
    every registered Module.  That lets the platform owner sell a POS-only
    account, combine several industry suites, or create a one-off/manual
    capability without changing code first.
    """
    company = get_object_or_404(Company, id=company_id)

    # Keep the friendly web features registered in the canonical module table.
    for code, name in WEB_FEATURES:
        Module.objects.get_or_create(code=code, defaults={"name": name, "is_core": False})

    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "add_custom":
            custom_name = request.POST.get("custom_name", "").strip()
            custom_code = request.POST.get("custom_code", "").strip().lower().replace(" ", "_")
            if not custom_name or not custom_code:
                messages.error(request, "Enter both a module name and module code.")
            else:
                module, created = Module.objects.get_or_create(
                    code=custom_code, defaults={"name": custom_name, "is_core": False}
                )
                if not created and module.name != custom_name:
                    module.name = custom_name
                    module.save(update_fields=["name"])
                CompanyModule.objects.update_or_create(
                    company=company, module=module, defaults={"is_active": True}
                )
                messages.success(request, f"{custom_name} added and enabled for {company.name}.")
            return redirect("webapp:platform_admin_manage_modules", company_id=company.id)

        enabled_ids = {int(x) for x in request.POST.getlist("modules") if x.isdigit()}
        for module in Module.objects.all():
            # Core modules remain active regardless of checkbox state.
            enabled = module.is_core or module.id in enabled_ids
            CompanyModule.objects.update_or_create(
                company=company, module=module, defaults={"is_active": enabled}
            )
        messages.success(request, f"Modules and features updated for {company.name}.")
        return redirect("webapp:platform_admin_company_detail", company_id=company.id)

    active_ids = set(
        CompanyModule.objects.filter(company=company, is_active=True).values_list("module_id", flat=True)
    )
    modules = list(Module.objects.all().order_by("is_core", "name"))
    module_rows = [(m, m.is_core or m.id in active_ids) for m in modules]

    # Show the complete RBAC catalogue here as a reference so the platform
    # owner can see every permission that may be assigned inside the tenant.
    permissions = Permission.objects.all().order_by("module", "label", "code")
    permission_groups = {}
    for perm in permissions:
        permission_groups.setdefault(perm.module or "general", []).append(perm)

    return render(request, "webapp/platform_admin/manage_modules.html", {
        "company": company,
        "module_rows": module_rows,
        "permission_groups": permission_groups,
        "web_feature_codes": {code for code, _ in WEB_FEATURES},
    })


@login_required
@superuser_required
def platform_admin_manage_business_suites(request, company_id):
    """Assign one or many industry suites to a tenant while keeping one consolidated company ledger."""
    company = get_object_or_404(Company, id=company_id)
    if request.method == "POST":
        selected = {int(x) for x in request.POST.getlist("business_types") if x.isdigit()}
        selected.add(company.business_type_id)
        for bt in BusinessType.objects.all():
            row, _ = CompanyBusinessType.objects.update_or_create(
                company=company, business_type=bt,
                defaults={"is_active": bt.id in selected, "is_primary": bt.id == company.business_type_id},
            )
            if bt.id in selected:
                for default in BusinessTypeDefaultModule.objects.filter(business_type=bt).select_related("module"):
                    CompanyModule.objects.update_or_create(company=company, module=default.module, defaults={"is_active": True})
        messages.success(request, "Business suites updated. Default modules for selected suites were enabled; accounting remains consolidated under this company.")
        return redirect("webapp:platform_admin_company_detail", company_id=company.id)
    active_ids = set(company.business_suites.filter(is_active=True).values_list("business_type_id", flat=True))
    active_ids.add(company.business_type_id)
    rows = [(bt, bt.id in active_ids, bt.id == company.business_type_id, business_group(bt.code)) for bt in BusinessType.objects.all().order_by("name")]
    return render(request, "webapp/platform_admin/manage_business_suites.html", {"company": company, "business_rows": rows})


# ================= PLATFORM ADMIN: BUSINESS SETUP =================

@login_required
@superuser_required
def platform_setup(request):
    User = get_user_model()
    return render(request, "webapp/platform_admin/setup.html", {
        "module_count": Module.objects.count(),
        "business_type_count": BusinessType.objects.count(),
        "user_count": User.objects.count(),
        "open_ticket_count": SupportTicket.objects.exclude(status__in=["resolved", "closed"]).count(),
        "email_configured": bool(settings.EMAIL_HOST and settings.EMAIL_HOST_USER),
        "stripe_configured": get_payment_gateway_config().stripe_enabled,
        "razorpay_configured": get_payment_gateway_config().razorpay_enabled,
    })


@login_required
@superuser_required
def platform_payment_gateway_settings(request):
    gateway_settings = PaymentGatewaySettings.load()
    form = PaymentGatewaySettingsForm(request.POST or None, instance=gateway_settings)
    if request.method == "POST" and form.is_valid():
        form.save(request.user)
        messages.success(request, "Payment gateway settings saved securely.")
        return redirect("webapp:platform_payment_gateway_settings")
    return render(request, "webapp/platform_admin/payment_gateway_settings.html", {
        "form": form,
        "gateway_settings": gateway_settings,
        "stripe_has_publishable": bool(gateway_settings.stripe_publishable_key_ciphertext),
        "stripe_has_secret": bool(gateway_settings.stripe_secret_key_ciphertext),
        "stripe_has_webhook": bool(gateway_settings.stripe_webhook_secret_ciphertext),
        "razorpay_has_id": bool(gateway_settings.razorpay_key_id_ciphertext),
        "razorpay_has_secret": bool(gateway_settings.razorpay_key_secret_ciphertext),
        "razorpay_has_webhook": bool(gateway_settings.razorpay_webhook_secret_ciphertext),
    })


@login_required
@superuser_required
def platform_module_list(request):
    return render(request, "webapp/platform_admin/module_list.html", {
        "modules": Module.objects.all().order_by("name"),
    })


@login_required
@superuser_required
def platform_module_form(request, module_id=None):
    module = get_object_or_404(Module, id=module_id) if module_id else None
    form = PlatformModuleForm(request.POST or None, instance=module)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Module {saved.name} saved.")
        return redirect("webapp:platform_module_list")
    return render(request, "webapp/platform_admin/simple_form.html", {
        "form": form, "form_title": "Edit module" if module else "Add module",
        "cancel_url": "webapp:platform_module_list",
    })


@login_required
@superuser_required
def platform_business_type_list(request):
    business_types = BusinessType.objects.prefetch_related("default_modules__module").order_by("name")
    return render(request, "webapp/platform_admin/business_type_list.html", {
        "business_types": business_types,
    })


@login_required
@superuser_required
def platform_business_type_form(request, business_type_id=None):
    business_type = get_object_or_404(BusinessType, id=business_type_id) if business_type_id else None
    form = PlatformBusinessTypeForm(request.POST or None, instance=business_type)
    if request.method == "POST" and form.is_valid():
        business_type = form.save()
        selected = set(form.cleaned_data["default_modules"].values_list("id", flat=True))
        BusinessTypeDefaultModule.objects.filter(business_type=business_type).exclude(module_id__in=selected).delete()
        for module_id in selected:
            BusinessTypeDefaultModule.objects.get_or_create(
                business_type=business_type, module_id=module_id,
            )
        messages.success(request, f"Business type {business_type.name} saved.")
        return redirect("webapp:platform_business_type_list")
    return render(request, "webapp/platform_admin/simple_form.html", {
        "form": form, "form_title": "Edit business type" if business_type else "Add business type",
        "cancel_url": "webapp:platform_business_type_list",
    })


@login_required
@superuser_required
def platform_user_list(request):
    User = get_user_model()
    users = User.objects.prefetch_related("memberships__company").order_by("email", "username")
    return render(request, "webapp/platform_admin/user_list.html", {"users": users})


@login_required
@superuser_required
def platform_support_list(request):
    tickets = SupportTicket.objects.select_related("company", "raised_by", "assigned_to").order_by("status", "-created_at")
    return render(request, "webapp/platform_admin/support_list.html", {"tickets": tickets})


@login_required
@superuser_required
def platform_support_edit(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id)
    form = PlatformSupportTicketForm(request.POST or None, instance=ticket)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Support ticket updated.")
        return redirect("webapp:platform_support_list")
    return render(request, "webapp/platform_admin/support_form.html", {"form": form, "ticket": ticket})


@login_required
@superuser_required
def platform_audit_list(request):
    logs = AuditLog.objects.all().select_related("company", "user").order_by("-timestamp")[:500]
    return render(request, "webapp/platform_admin/audit_list.html", {"logs": logs})

@login_required
@superuser_required
def platform_commercial_control(request):
    """Owner command centre: packages, limits, white-label and multi-suite sales overview."""
    from apps.subscriptions.models import ClientCommercialProfile
    companies = Company.objects.select_related('business_type').order_by('-created_at')
    rows=[]
    for c in companies:
        profile,_=ClientCommercialProfile.objects.get_or_create(company=c)
        suites=list(c.business_suites.filter(is_active=True).select_related('business_type'))
        rows.append((c, profile, suites, c.active_modules().count()))
    return render(request,'webapp/platform_admin/commercial_control.html',{
      'rows':rows,'module_count':Module.objects.count(),'business_type_count':BusinessType.objects.count(),
      'multi_business_count':CompanyBusinessType.objects.filter(is_active=True).values('company_id').annotate(n=Count('id')).filter(n__gt=1).count(),
      'plan_count':SubscriptionPlan.objects.filter(is_active=True).count(),
    })

@login_required
@superuser_required
def platform_client_commercial_profile(request, company_id):
    from apps.subscriptions.models import ClientCommercialProfile
    from apps.webapp.forms import ClientCommercialProfileForm
    company=get_object_or_404(Company,id=company_id)
    profile,_=ClientCommercialProfile.objects.get_or_create(company=company)
    form=ClientCommercialProfileForm(request.POST or None,instance=profile)
    if request.method=='POST' and form.is_valid():
        form.save(); messages.success(request,'Commercial limits and white-label settings updated.')
        return redirect('webapp:platform_admin_company_detail',company_id=company.id)
    return render(request,'webapp/platform_admin/commercial_profile.html',{'company':company,'form':form})

@login_required
@superuser_required
def platform_permission_catalogue(request):
    groups={}
    for p in Permission.objects.all().order_by('module','label'):
        groups.setdefault(p.module or 'general',[]).append(p)
    return render(request,'webapp/platform_admin/permission_catalogue.html',{'permission_groups':groups,'permission_count':Permission.objects.count()})


@login_required
@superuser_required
def platform_admin_company_restore(request, company_id):
    from django.views.decorators.http import require_POST
    if request.method != "POST":
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])
    company = get_object_or_404(Company, pk=company_id)
    company.is_active = True
    company.archived_at = None
    company.save(update_fields=["is_active", "archived_at"])
    messages.success(request, f"{company.name} restored.")
    return redirect("webapp:platform_admin_company_detail", company_id=company.pk)


@login_required
@superuser_required
def platform_admin_roles(request, company_id):
    company = get_object_or_404(Company, pk=company_id)
    roles = Role.objects.filter(company=company).prefetch_related("permissions__permission").order_by("name")
    return render(request, "webapp/platform_admin/roles.html", {"company": company, "roles": roles})


@login_required
@superuser_required
def platform_admin_role_permissions(request, company_id, role_id):
    company = get_object_or_404(Company, pk=company_id)
    role = get_object_or_404(Role, pk=role_id, company=company)
    permissions = Permission.objects.order_by("module", "label")
    if request.method == "POST":
        from django.core.exceptions import PermissionDenied
        posted = request.POST.getlist("permissions")
        valid = set(permissions.values_list("pk", flat=True))
        try:
            selected = {int(pk) for pk in posted}
        except (TypeError, ValueError):
            raise PermissionDenied("Invalid permission selection")
        if not selected.issubset(valid):
            raise PermissionDenied("Unknown permission")
        if role.name == "Owner" and selected != valid:
            messages.error(request, "The tenant Owner role must retain all permissions.")
        else:
            from apps.tenants.models import RolePermission
            with transaction.atomic():
                RolePermission.objects.filter(role=role).exclude(permission_id__in=selected).delete()
                RolePermission.objects.bulk_create(
                    [RolePermission(role=role, permission_id=pk) for pk in selected],
                    ignore_conflicts=True,
                )
            messages.success(request, f"Permissions for {role.name} updated.")
            return redirect("webapp:platform_admin_roles", company_id=company.pk)
    granted = set(role.permissions.values_list("permission_id", flat=True))
    return render(request, "webapp/platform_admin/role_permissions.html", {
        "company": company, "role": role, "permissions": permissions, "granted": granted,
    })
