from django import forms

from apps.inventory.models import ProductCategory, Product, Brand, Unit
from apps.customers.models import Customer
from apps.verticals.mobile_shop.models import (
    MobileUnit, MobileRepairJob, MobileRepairPart, MobileTradeIn,
    MobileWarrantyClaim, MobileInstallmentPayment,
)
from apps.verticals.gym.models import MembershipPlan, GymMember
from apps.verticals.spa.models import SpaService, Appointment
from apps.employees.models import Employee
from apps.verticals.textile.models import FabricDetail, Measurement, TailoringOrder
from apps.verticals.vehicle_wash.models import Vehicle, WashPackage
from apps.verticals.sports_shop.models import SportsProductDetail
from apps.verticals.cycle_shop.models import CycleUnit, ServiceTicket
from apps.verticals.saloon.models import SaloonService, ServicePackage as SaloonServicePackage, CustomerPackage as SaloonCustomerPackage, Appointment as SaloonAppointment, ServiceClientProfile, ServiceCase, ServiceCaseNote
from apps.verticals.beauty_parlour.models import BeautyService, Appointment as BeautyAppointment
from apps.verticals.medical_shop.models import MedicineBatch
from apps.verticals.protein_shop.models import ProteinBatch
from apps.verticals.construction.models import Project, Contractor, ProjectExpense, ProjectMilestone, ProjectTask, ProjectTimesheet
from apps.inventory.models import Warehouse
from apps.suppliers.models import Supplier
from apps.purchases.models import Purchase, SupplierPayment
from apps.sales.models import SalesInvoice, SalesReturn
from apps.expenses.models import ExpenseCategory, Expense
from apps.tenants.models import Role, Permission, CompanyMembership, Company
from apps.subscriptions.models import Subscription, SubscriptionPlan, SubscriptionPayment
from apps.modules.models import BusinessType, Module, CompanyModule
from apps.platform_admin.models import SupportTicket
from apps.modules.catalog import BUSINESS_TYPE_CHOICES
from apps.verticals.restaurant.models import DiningArea, DiningTable, FoodWaste, KitchenStation, MenuModifier, MenuModifierGroup, MenuModifierOption, RestaurantMenuItem, RestaurantProfile, RecipeIngredient, RestaurantCombo, RestaurantComboItem, RestaurantOrder, RestaurantShift, TableReservation, DeliveryIntegration

# Toggleable webapp-level features an admin can enable/disable per client.
# Distinct from apps.modules' older backend/vertical module codes (kept as "webui_*"
# to avoid colliding with those), and checked purely for UI/URL visibility here.
WEB_FEATURES = [
    ("webui_pos", "Point of Sale (POS)"),
    ("webui_returns_refunds", "Returns & Refunds"),
    ("webui_coupons_loyalty", "Coupons & Loyalty Program"),
    ("webui_expenses", "Expense Management"),
    ("webui_suppliers_purchases", "Suppliers & Purchases"),
    ("webui_branches", "Multi-Branch Support"),
    ("webui_team_roles", "Team & Roles (Staff logins)"),
    ("webui_analytics", "Analytics & Charts"),
]
from apps.sales.models import Coupon
from apps.customers.models import LoyaltyAccount


class CategoryForm(forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ["name"]


class ProductForm(forms.ModelForm):
    attributes_text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}), required=False,
        label="Extra details (optional)",
        help_text="One per line, e.g. Material: Cotton",
    )

    class Meta:
        model = Product
        fields = [
            "sku", "name", "category", "brand", "unit", "cost_price", "selling_price",
            "reorder_level", "size", "colour", "material", "design",
        ]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["category"].queryset = ProductCategory.objects.for_company(company)
            self.fields["brand"].queryset = Brand.objects.for_company(company)
            self.fields["unit"].queryset = Unit.objects.for_company(company)
        self.fields["category"].required = False
        self.fields["brand"].required = False
        if self.instance and self.instance.pk and self.instance.attributes:
            lines = [f"{k}: {v}" for k, v in self.instance.attributes.items()]
            self.fields["attributes_text"].initial = "\n".join(lines)

    def clean_attributes_text(self):
        text = self.cleaned_data.get("attributes_text", "")
        attrs = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                attrs[key.strip()] = value.strip()
            else:
                attrs[line] = ""
        return attrs

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.attributes = self.cleaned_data.get("attributes_text", {})
        if commit:
            obj.save()
        return obj


class MobileProductForm(ProductForm):
    ITEM_TYPES = [("handset", "Mobile Handset"), ("accessory", "Accessory"), ("spare_part", "Spare Part"), ("service", "Repair Service")]
    item_type = forms.ChoiceField(choices=ITEM_TYPES)
    model_number = forms.CharField(max_length=100, required=False)
    ram = forms.CharField(max_length=50, required=False, label="RAM")
    storage = forms.CharField(max_length=50, required=False)
    network = forms.CharField(max_length=50, required=False, help_text="e.g. 5G")
    battery = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        attrs = self.instance.attributes if self.instance and self.instance.pk else {}
        for key in ("item_type", "model_number", "ram", "storage", "network", "battery"):
            if attrs.get(key):
                self.fields[key].initial = attrs[key]

    def save(self, commit=True):
        obj = super().save(commit=False)
        attrs = dict(obj.attributes or {})
        for key in ("item_type", "model_number", "ram", "storage", "network", "battery"):
            attrs[key] = self.cleaned_data.get(key, "")
        obj.attributes = attrs
        item_type = self.cleaned_data["item_type"]
        obj.is_stock_tracked = item_type not in {"handset", "service"}
        obj.tracking_type = "none" if not obj.is_stock_tracked else "basic"
        if commit:
            obj.save()
        return obj


class BusinessProductForm(ProductForm):
    """Industry-aware product master while retaining the shared stock/POS engine."""
    INDUSTRY_FIELDS = {
        "general_retail": ("brand_code", "barcode_type", "shelf_location"),
        "retail_shop": ("brand_code", "barcode_type", "shelf_location"),
        "clothing_store": ("gender", "size_range", "material_spec", "design_reference", "season_collection"),
        "ladies_fashion_boutique": ("size_range", "colour_range", "material_spec", "design_reference", "season_collection"),
        "book_store": ("isbn", "author", "publisher", "grade_subject"),
        "perfume_shop": ("fragrance_family", "volume_ml", "concentration"),
        "watch_shop": ("model_number", "movement", "strap_material", "water_resistance"),
        "jewelry_shop": ("weight_grams", "purity", "stone_details", "making_charge"),
        "auto_spare_parts": ("part_number", "oem_number", "compatible_models"),
        "car_showroom": ("vin", "chassis_number", "model_year", "transmission", "mileage"),
        "electronics_store": ("model_number", "serial_required", "warranty_months", "technical_specs"),
        "computer_shop": ("model_number", "serial_required", "warranty_months", "technical_specs"),
        "bakery": ("production_date", "expiry_date", "ingredients", "allergens"),
        "grocery_store": ("expiry_date", "pack_size", "country_of_origin"),
        "supermarket": ("expiry_date", "pack_size", "country_of_origin"),
        "cosmetics_store": ("shade", "expiry_date", "skin_type"),
        "medical_equipment_store": ("model_number", "serial_required", "warranty_months", "certification"),
        "pet_shop": ("pet_type", "age_group", "expiry_date"),
        "flower_shop": ("flower_type", "occasion", "care_instructions"),
        "furniture_store": ("dimensions", "material_spec", "assembly_required"),
        "hardware_store": ("part_number", "dimensions", "technical_specs"),
        "printing_shop": ("paper_size", "gsm", "print_type"),
        "manufacturing": ("bom_reference", "production_lead_days", "quality_standard"),
        "industrial_services": ("model_number", "serial_required", "technical_specs", "certification", "service_interval_days"),
        "trading_company": ("supplier_code", "hs_code", "minimum_order_quantity", "country_of_origin", "lead_time_days"),
        "wholesale_business": ("supplier_code", "minimum_order_quantity", "carton_reference", "lead_time_days"),
        "import_export": ("supplier_code", "hs_code", "country_of_origin", "minimum_order_quantity", "lead_time_days"),
        "footwear_store": ("gender", "age_group", "material_spec", "size_range"),
        "baby_products_store": ("age_group", "size_range", "material_spec", "safety_standard"),
        "toys_gift_shop": ("age_group", "material_spec", "safety_standard", "occasion"),
        "home_appliances_store": ("model_number", "serial_required", "warranty_months", "technical_specs"),
        "electrical_plumbing_store": ("part_number", "dimensions", "technical_specs", "certification"),
        "building_materials_store": ("dimensions", "material_spec", "quality_standard", "country_of_origin"),
        "tyre_battery_shop": ("model_number", "compatible_models", "dimensions", "warranty_months", "production_date"),
        "fish_meat_shop": ("product_type", "weight_grams", "expiry_date", "country_of_origin"),
        "fruits_vegetables_shop": ("product_type", "quality_standard", "expiry_date", "country_of_origin"),
        "ecommerce_store": ("marketplace_sku", "dimensions", "weight_grams", "country_of_origin"),
        "mobile_accessories_shop": ("model_number", "compatible_models", "warranty_months", "technical_specs"),
        "uniform_shop": ("size_range", "material_spec", "design_reference", "organization_name"),
        "kitchenware_store": ("dimensions", "material_spec", "technical_specs"),
        "musical_instruments_store": ("instrument_type", "model_number", "serial_required", "warranty_months"),
        "agricultural_supplies_store": ("product_type", "expiry_date", "application_details", "country_of_origin"),
        "optical_shop": ("frame_material", "lens_type", "power_range", "model_number", "warranty_months"),
        "fuel_station": ("fuel_grade", "tank_number", "unit_density", "country_of_origin"),
        "restaurant": ("item_type", "preparation_minutes", "ingredients", "allergens"),
        "cafe_juice_shop": ("item_type", "preparation_minutes", "ingredients", "allergens"),
    }
    FIELD_LABELS = {
        "isbn": "ISBN", "author": "Author", "publisher": "Publisher", "grade_subject": "Grade / Subject",
        "fragrance_family": "Fragrance family", "volume_ml": "Volume (ml)", "concentration": "Concentration",
        "model_number": "Model number", "movement": "Movement", "strap_material": "Strap material",
        "water_resistance": "Water resistance", "weight_grams": "Weight (grams)", "purity": "Purity",
        "stone_details": "Stone details", "making_charge": "Making charge", "part_number": "Part number",
        "oem_number": "OEM number", "compatible_models": "Compatible models", "vin": "VIN",
        "chassis_number": "Chassis number", "model_year": "Model year", "transmission": "Transmission",
        "mileage": "Mileage", "serial_required": "Serial tracking required", "warranty_months": "Warranty months",
        "technical_specs": "Technical specifications", "production_date": "Production date", "expiry_date": "Expiry date",
        "ingredients": "Ingredients", "allergens": "Allergens", "pack_size": "Pack size",
        "country_of_origin": "Country of origin", "shade": "Shade", "skin_type": "Skin type",
        "certification": "Certification", "pet_type": "Pet type", "age_group": "Age group",
        "flower_type": "Flower type", "occasion": "Occasion", "care_instructions": "Care instructions",
        "dimensions": "Dimensions", "material_spec": "Material", "assembly_required": "Assembly required",
        "paper_size": "Paper size", "gsm": "GSM", "print_type": "Print type", "bom_reference": "BOM reference",
        "production_lead_days": "Production lead days", "quality_standard": "Quality standard",
        "gender": "Gender", "size_range": "Size range", "safety_standard": "Safety standard",
        "product_type": "Product type", "marketplace_sku": "Marketplace SKU",
        "design_reference": "Design reference", "organization_name": "School / Organization",
        "instrument_type": "Instrument type", "application_details": "Application / Usage",
        "frame_material": "Frame material", "lens_type": "Lens type", "power_range": "Power range",
        "fuel_grade": "Fuel grade", "tank_number": "Tank number", "unit_density": "Density",
        "item_type": "Menu item type", "preparation_minutes": "Preparation time (minutes)",
        "brand_code": "Brand / manufacturer code", "barcode_type": "Barcode type",
        "shelf_location": "Shelf / bin location", "colour_range": "Colour range",
        "season_collection": "Season / collection", "supplier_code": "Supplier code",
        "hs_code": "HS / customs code", "minimum_order_quantity": "Minimum order quantity",
        "lead_time_days": "Lead time (days)", "carton_reference": "Carton / pack reference",
        "service_interval_days": "Service interval (days)",
    }
    wholesale_price = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
    carton_quantity = forms.DecimalField(max_digits=12, decimal_places=3, required=False)

    def __init__(self, *args, company=None, **kwargs):
        self.business_code = company.business_type.code if company else "general_retail"
        super().__init__(*args, company=company, **kwargs)
        active = set(self.INDUSTRY_FIELDS.get(self.business_code, ()))
        for name, label in self.FIELD_LABELS.items():
            if name in active:
                if name in {"serial_required", "assembly_required"}:
                    self.fields[name] = forms.BooleanField(required=False, label=label)
                elif name in {"production_date", "expiry_date"}:
                    self.fields[name] = forms.DateField(required=False, label=label, widget=forms.DateInput(attrs={"type": "date"}))
                elif name in {"weight_grams", "making_charge", "mileage"}:
                    self.fields[name] = forms.DecimalField(required=False, label=label, max_digits=12, decimal_places=2)
                elif name in {"warranty_months", "model_year", "production_lead_days", "preparation_minutes", "lead_time_days", "service_interval_days"}:
                    self.fields[name] = forms.IntegerField(required=False, label=label)
                elif name in {"minimum_order_quantity"}:
                    self.fields[name] = forms.DecimalField(required=False, label=label, max_digits=12, decimal_places=3)
                else:
                    self.fields[name] = forms.CharField(required=False, label=label, widget=forms.Textarea(attrs={"rows": 2}) if name in {"technical_specs", "compatible_models", "ingredients", "care_instructions"} else None)
                if self.instance and self.instance.pk:
                    self.fields[name].initial = (self.instance.attributes or {}).get(name, "")
        attrs = self.instance.attributes if self.instance and self.instance.pk else {}
        self.fields["wholesale_price"].initial = attrs.get("wholesale_price")
        self.fields["carton_quantity"].initial = attrs.get("carton_quantity")

    def save(self, commit=True):
        obj = super().save(commit=False)
        attrs = dict(obj.attributes or {})
        for name in self.INDUSTRY_FIELDS.get(self.business_code, ()):
            value = self.cleaned_data.get(name)
            attrs[name] = value.isoformat() if hasattr(value, "isoformat") else value
        for name in ("wholesale_price", "carton_quantity"):
            value = self.cleaned_data.get(name)
            attrs[name] = str(value) if value is not None else ""
        obj.attributes = attrs
        if self.cleaned_data.get("serial_required"):
            obj.tracking_type = "serial"
        if commit:
            obj.save()
        return obj


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ["name"]


class VariantForm(forms.Form):
    size = forms.CharField(max_length=50, required=False, label="Size (e.g. S, M, L, XL)")
    colour = forms.CharField(max_length=50, required=False, label="Colour")
    material = forms.CharField(max_length=100, required=False, label="Material")
    design = forms.CharField(max_length=100, required=False, label="Design")
    sku = forms.CharField(max_length=50)
    cost_price = forms.DecimalField(max_digits=12, decimal_places=2, initial=0)
    selling_price = forms.DecimalField(max_digits=12, decimal_places=2)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("size") and not cleaned.get("colour"):
            raise forms.ValidationError("Enter at least a size or colour for this variant.")
        cleaned["variant_label"] = " / ".join(
            value for value in (cleaned.get("colour"), cleaned.get("size")) if value
        )
        return cleaned


class MobileUnitForm(forms.ModelForm):
    class Meta:
        model = MobileUnit
        fields = ["product", "imei", "serial_number", "condition", "warranty_months", "purchase_price", "warehouse", "status"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["product"].queryset = Product.objects.for_company(company)
            self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)


class MobileBulkIMEIForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none())
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none(), required=False)
    purchase_price = forms.DecimalField(max_digits=12, decimal_places=2)
    warranty_months = forms.IntegerField(min_value=0, initial=12)
    condition = forms.ChoiceField(choices=MobileUnit.CONDITION, initial="new")
    imeis = forms.CharField(widget=forms.Textarea(attrs={"rows": 10}), help_text="One IMEI per line. Optional serial: IMEI,SERIAL")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.for_company(company).filter(attributes__item_type="handset")
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)
        self.fields["supplier"].queryset = Supplier.objects.for_company(company).filter(is_active=True)

    def clean_imeis(self):
        rows, seen = [], set()
        for raw in self.cleaned_data["imeis"].splitlines():
            raw = raw.strip()
            if not raw:
                continue
            imei, _, serial = raw.partition(",")
            imei = imei.strip()
            if not imei or imei in seen:
                raise forms.ValidationError("IMEI values must be non-empty and unique.")
            seen.add(imei)
            rows.append((imei, serial.strip()))
        if not rows:
            raise forms.ValidationError("Enter at least one IMEI.")
        return rows


class MobileRepairJobForm(forms.ModelForm):
    class Meta:
        model = MobileRepairJob
        fields = ["customer", "mobile_unit", "device_description", "imei", "reported_issue", "diagnosis", "estimated_cost", "assigned_technician", "warehouse", "service_product", "is_warranty_job", "status"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company)
        self.fields["mobile_unit"].queryset = MobileUnit.objects.for_company(company)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)
        self.fields["service_product"].queryset = Product.objects.for_company(company).filter(is_stock_tracked=False)
        self.fields["assigned_technician"].queryset = self.fields["assigned_technician"].queryset.filter(memberships__company=company, memberships__is_active=True).distinct()


class MobileRepairPartForm(forms.ModelForm):
    class Meta:
        model = MobileRepairPart
        fields = ["product", "quantity", "unit_cost", "unit_price"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.for_company(company).filter(is_stock_tracked=True)


class MobileWarrantyClaimForm(forms.ModelForm):
    class Meta:
        model = MobileWarrantyClaim
        fields = ["unit", "customer", "issue", "status", "resolution", "received_date", "resolved_date"]
        widgets = {"received_date": forms.DateInput(attrs={"type": "date"}), "resolved_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unit"].queryset = MobileUnit.objects.for_company(company).filter(status="sold")
        self.fields["customer"].queryset = Customer.objects.for_company(company)


class MobileTradeInForm(forms.ModelForm):
    class Meta:
        model = MobileTradeIn
        fields = ["customer", "product", "imei", "serial_number", "condition", "quoted_value", "accepted_value", "warehouse"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company)
        self.fields["product"].queryset = Product.objects.for_company(company).filter(attributes__item_type="handset")
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)


class MobileInstallmentPaymentForm(forms.ModelForm):
    class Meta:
        model = MobileInstallmentPayment
        fields = ["amount", "date", "method"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "address"]


class SellUnitForm(forms.Form):
    buyer = forms.ModelChoiceField(queryset=Customer.objects.none(), label="Customer")
    sold_price = forms.DecimalField(max_digits=10, decimal_places=2, label="Sale price")
    sold_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["buyer"].queryset = Customer.objects.for_company(company).filter(is_active=True)


class MembershipPlanForm(forms.Form):
    name = forms.CharField(max_length=100)
    duration_days = forms.IntegerField(min_value=1, label="Duration (days)")
    price = forms.DecimalField(max_digits=10, decimal_places=2)


class EnrollMemberForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    membership_plan = forms.ModelChoiceField(queryset=MembershipPlan.objects.none(), label="Plan")
    join_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            already_members = GymMember.objects.for_company(company).values_list("customer_id", flat=True)
            self.fields["customer"].queryset = (
                Customer.objects.for_company(company).filter(is_active=True).exclude(id__in=already_members)
            )
            self.fields["membership_plan"].queryset = MembershipPlan.objects.for_company(company).filter(is_active=True)


class RenewMemberForm(forms.Form):
    membership_plan = forms.ModelChoiceField(queryset=MembershipPlan.objects.none(), label="Plan")
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["membership_plan"].queryset = MembershipPlan.objects.for_company(company).filter(is_active=True)


class NewCustomerQuickForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email"]

class SpaServiceForm(forms.Form):
    name = forms.CharField(max_length=150)
    duration_minutes = forms.IntegerField(min_value=1)
    price = forms.DecimalField(max_digits=10, decimal_places=2)


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["name", "phone", "role_title", "salary", "joined_date"]
        widgets = {"joined_date": forms.DateInput(attrs={"type": "date"})}


class BookAppointmentForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    service = forms.ModelChoiceField(queryset=SpaService.objects.none())
    therapist = forms.ModelChoiceField(queryset=Employee.objects.none(), label="Therapist")
    scheduled_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    commission_rate_percent = forms.DecimalField(
        max_digits=5, decimal_places=2, required=False, initial=0, label="Therapist commission %"
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
            self.fields["service"].queryset = SpaService.objects.for_company(company).filter(is_active=True)
            self.fields["therapist"].queryset = Employee.objects.for_company(company).filter(is_active=True)

class RegisterClientForm(forms.Form):
    BUSINESS_TYPES = BUSINESS_TYPE_CHOICES
    _LEGACY_BUSINESS_TYPES = [
        ("mobile_shop", "Mobile Shop"),
        ("gym", "Gym / Fitness Center"),
        ("spa", "Spa"),
        ("textile", "Textile"),
        ("vehicle_wash", "Vehicle Wash / Car Wash"),
        ("sports_shop", "Sports Shop"),
        ("cycle_shop", "Cycle Shop"),
        ("saloon", "Saloon / Barber Shop"),
        ("beauty_parlour", "Beauty Parlour / Beauty Salon"),
        ("medical_shop", "Medical Shop / Pharmacy"),
        ("protein_shop", "Protein & Supplements Shop"),
        ("construction", "Construction / Contracting Company"),
        ("watch_shop", "Watch Shop"),
        ("perfume_shop", "Perfume Shop"),
        ("book_store", "Book & Stationery Shop"),
        ("tailoring_shop", "Tailoring Shop"),
        ("retail_shop", "Retail Shop"),
        ("supermarket", "Supermarket"),
        ("grocery_store", "Grocery Store"),
        ("clothing_store", "Clothing Store"),
        ("ladies_fashion_boutique", "Ladies Fashion / Boutique"),
        ("electronics_store", "Electronics Store"),
        ("computer_shop", "Computer Shop"),
        ("furniture_store", "Furniture Store"),
        ("hardware_store", "Hardware Store"),
        ("cosmetics_store", "Cosmetics Store"),
        ("jewelry_shop", "Jewelry Shop"),
        ("auto_spare_parts", "Auto Spare Parts"),
        ("medical_equipment_store", "Medical Equipment Store"),
        ("flower_shop", "Flower Shop"),
        ("pet_shop", "Pet Shop"),
        ("bakery", "Bakery"),
        ("trading_company", "Trading Company"),
        ("wholesale_business", "Wholesale Business"),
        ("import_export", "Import & Export"),
        ("car_showroom", "Car Showroom"),
        ("printing_shop", "Printing Shop"),
        ("manufacturing", "Manufacturing"),
        ("industrial_services", "Industrial Services"),
        # -- service / appointment businesses --
        ("dental_clinic", "Dental Clinic"),
        ("medical_clinic", "Medical Clinic"),
        ("physiotherapy_center", "Physiotherapy Center"),
        ("veterinary_clinic", "Veterinary Clinic"),
        ("photography_studio", "Photography / Videography Studio"),
        ("driving_school", "Driving School"),
        ("tuition_center", "Tuition Center"),
        ("consultancy", "Consultancy"),
        ("auto_garage", "Auto Garage"),
        ("repair_services", "Repair Services"),
        ("home_services", "Home Services"),
        ("laundry_dry_cleaning", "Laundry / Dry Cleaning"),
        # -- project / agency businesses --
        ("advertising_agency", "Advertising Agency"),
        ("digital_marketing_agency", "Digital Marketing Agency"),
        ("web_development", "Web Development"),
        ("it_services", "IT Services"),
        ("software_company", "Software Company"),
        ("accounting_audit", "Accounting / Audit"),
        ("recruitment_agency", "Recruitment Agency"),
        ("security_services", "Security Services"),
        ("event_management", "Event Management"),
        ("cleaning_company", "Cleaning Company"),
        ("maintenance_company", "Maintenance Company"),
        ("landscaping_company", "Landscaping Company"),
    ]

    business_name = forms.CharField(max_length=255, label="Business name")
    business_type = forms.ChoiceField(choices=BUSINESS_TYPES)
    country = forms.CharField(max_length=100, label="Country")
    plan = forms.ModelChoiceField(queryset=SubscriptionPlan.objects.none(), label="Pricing plan", required=False,
                                   help_text="Leave blank to assign a plan later")
    owner_username = forms.CharField(max_length=150, label="Login username")
    owner_email = forms.EmailField(required=True, label="Email")
    owner_password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Login password")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = SubscriptionPlan.objects.filter(is_active=True).order_by("country", "price")

    def clean_owner_username(self):
        from django.contrib.auth import get_user_model
        username = self.cleaned_data["owner_username"].strip()
        if get_user_model().objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_owner_email(self):
        from django.contrib.auth import get_user_model
        email = self.cleaned_data["owner_email"].strip()
        if get_user_model().objects.filter(email=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

class FabricForm(forms.Form):
    sku = forms.CharField(max_length=50)
    name = forms.CharField(max_length=255)
    category = forms.ModelChoiceField(queryset=ProductCategory.objects.none(), required=False)
    unit = forms.ModelChoiceField(queryset=Unit.objects.none())
    cost_price = forms.DecimalField(max_digits=12, decimal_places=2, initial=0)
    selling_price = forms.DecimalField(max_digits=12, decimal_places=2)

    fabric_type = forms.ChoiceField(choices=FabricDetail.FABRIC_TYPE)
    color = forms.CharField(max_length=50, required=False)
    design = forms.CharField(max_length=100, required=False)
    material = forms.CharField(max_length=100, required=False, help_text="Cotton, silk, polyester...")
    length_per_unit = forms.DecimalField(max_digits=8, decimal_places=2, required=False, label="Length per unit (m)")
    width_inches = forms.DecimalField(max_digits=6, decimal_places=2, required=False, label="Width (inches)")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["category"].queryset = ProductCategory.objects.for_company(company)
            self.fields["unit"].queryset = Unit.objects.for_company(company)


class MeasurementForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    garment_type = forms.CharField(max_length=50, help_text="shirt, pant, blouse, kurta...")
    chest = forms.DecimalField(max_digits=6, decimal_places=2, required=False)
    waist = forms.DecimalField(max_digits=6, decimal_places=2, required=False)
    sleeve = forms.DecimalField(max_digits=6, decimal_places=2, required=False)
    length = forms.DecimalField(max_digits=6, decimal_places=2, required=False)
    taken_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)


class TailoringOrderForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    measurement = forms.ModelChoiceField(queryset=Measurement.objects.none(), required=False)
    fabric_product = forms.ModelChoiceField(queryset=Product.objects.none(), required=False, label="Fabric (if shop-provided)")
    order_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    expected_delivery_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    price = forms.DecimalField(max_digits=10, decimal_places=2)
    notes = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
            self.fields["measurement"].queryset = Measurement.objects.for_company(company).order_by("-taken_on")
            self.fields["fabric_product"].queryset = Product.objects.for_company(company).filter(fabric_detail__isnull=False)

class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["customer", "vehicle_number", "vehicle_type", "make", "model", "color"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)


class WashPackageForm(forms.ModelForm):
    class Meta:
        model = WashPackage
        fields = ["name", "vehicle_type", "price", "duration_minutes", "description"]


class BookWashForm(forms.Form):
    vehicle = forms.ModelChoiceField(queryset=Vehicle.objects.none())
    package = forms.ModelChoiceField(queryset=WashPackage.objects.none())
    staff = forms.ModelChoiceField(queryset=Employee.objects.none(), required=False)
    scheduled_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    price = forms.DecimalField(max_digits=10, decimal_places=2, required=False, help_text="Leave blank to use the package price")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["vehicle"].queryset = Vehicle.objects.for_company(company)
            self.fields["package"].queryset = WashPackage.objects.for_company(company).filter(is_active=True)
            self.fields["staff"].queryset = Employee.objects.for_company(company).filter(is_active=True)

# ---------------- Sports Shop ----------------

class SportsProductForm(forms.Form):
    sku = forms.CharField(max_length=50)
    name = forms.CharField(max_length=255)
    category = forms.ModelChoiceField(queryset=ProductCategory.objects.none(), required=False)
    unit = forms.ModelChoiceField(queryset=Unit.objects.none())
    cost_price = forms.DecimalField(max_digits=12, decimal_places=2, initial=0)
    selling_price = forms.DecimalField(max_digits=12, decimal_places=2)

    sport_category = forms.ChoiceField(choices=SportsProductDetail.SPORT_CATEGORY)
    size = forms.CharField(max_length=20, required=False)
    gender = forms.ChoiceField(choices=SportsProductDetail.GENDER)
    material = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["category"].queryset = ProductCategory.objects.for_company(company)
            self.fields["unit"].queryset = Unit.objects.for_company(company)


# ---------------- Cycle Shop ----------------

class CycleUnitForm(forms.ModelForm):
    class Meta:
        model = CycleUnit
        fields = ["product", "serial_number", "warranty_months", "purchase_price", "status"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["product"].queryset = Product.objects.for_company(company)


class SellCycleForm(forms.Form):
    buyer = forms.ModelChoiceField(queryset=Customer.objects.none(), label="Customer")
    sold_price = forms.DecimalField(max_digits=10, decimal_places=2, label="Sale price")
    sold_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["buyer"].queryset = Customer.objects.for_company(company).filter(is_active=True)


class ServiceTicketForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    cycle_unit = forms.ModelChoiceField(queryset=CycleUnit.objects.none(), required=False, label="Cycle (if bought here)")
    cycle_description = forms.CharField(max_length=255, required=False, label="Cycle description (if not bought here)")
    issue_description = forms.CharField(widget=forms.Textarea)
    staff = forms.ModelChoiceField(queryset=Employee.objects.none(), required=False)
    received_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
            self.fields["cycle_unit"].queryset = CycleUnit.objects.for_company(company)
            self.fields["staff"].queryset = Employee.objects.for_company(company).filter(is_active=True)


# ---------------- Saloon ----------------

class SaloonServiceForm(forms.Form):
    name = forms.CharField(max_length=150)
    duration_minutes = forms.IntegerField(min_value=1)
    price = forms.DecimalField(max_digits=10, decimal_places=2)


class BookSaloonAppointmentForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    service = forms.ModelChoiceField(queryset=SaloonService.objects.none())
    stylist = forms.ModelChoiceField(queryset=Employee.objects.none())
    scheduled_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    commission_rate_percent = forms.DecimalField(max_digits=5, decimal_places=2, required=False, initial=0, label="Stylist commission %")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
            self.fields["service"].queryset = SaloonService.objects.for_company(company).filter(is_active=True)
            self.fields["stylist"].queryset = Employee.objects.for_company(company).filter(is_active=True)


class ServiceClientProfileForm(forms.ModelForm):
    details_text = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), required=False,
        label="Additional details", help_text="One per line, e.g. Blood group: O+ or Vehicle make: Toyota")
    class Meta:
        model = ServiceClientProfile
        fields = ["customer", "profile_type", "subject_name", "reference_code", "date_of_birth", "identifier", "notes", "is_active"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company)
        from apps.modules.catalog import business_profile
        profile = business_profile(company.business_type.code)
        profile_type = profile.get("profile_type", "person")
        if not self.is_bound and not (self.instance and self.instance.pk):
            self.fields["profile_type"].initial = profile_type
        subject_labels = {"person": "Patient / person name", "student": "Student name", "pet": "Pet name",
                          "vehicle": "Vehicle name / model", "asset": "Asset / item name",
                          "organization": "Client / organization name"}
        identifier_labels = {"person": "MRN / ID", "student": "Student ID", "pet": "Registration / microchip",
                             "vehicle": "Plate / VIN", "asset": "Serial / asset tag",
                             "organization": "Registration / reference"}
        self.fields["subject_name"].label = subject_labels[profile_type]
        self.fields["identifier"].label = identifier_labels[profile_type]
        if self.instance and self.instance.pk:
            self.fields["details_text"].initial = "\n".join(f"{k}: {v}" for k, v in self.instance.details.items())
    def clean_details_text(self):
        result = {}
        for line in self.cleaned_data.get("details_text", "").splitlines():
            key, sep, value = line.partition(":")
            if key.strip(): result[key.strip()] = value.strip() if sep else ""
        return result
    def save(self, commit=True):
        obj = super().save(commit=False); obj.details = self.cleaned_data.get("details_text", {})
        if commit: obj.save()
        return obj


class ServiceCaseForm(forms.ModelForm):
    class Meta:
        model = ServiceCase
        fields = ["profile", "title", "case_type", "description", "assigned_staff", "status", "opened_date", "due_date", "closed_date"]
        widgets = {"opened_date": forms.DateInput(attrs={"type": "date"}), "due_date": forms.DateInput(attrs={"type": "date"}), "closed_date": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.modules.catalog import business_profile
        profile = business_profile(company.business_type.code)
        self.fields["title"].label = profile.get("work_label", "Case / work order")
        self.fields["profile"].queryset = ServiceClientProfile.objects.for_company(company).filter(is_active=True)
        self.fields["assigned_staff"].queryset = Employee.objects.for_company(company).filter(is_active=True)


class ServiceCaseNoteForm(forms.ModelForm):
    class Meta:
        model = ServiceCaseNote
        fields = ["date", "note_type", "notes", "outcome", "next_follow_up"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "next_follow_up": forms.DateInput(attrs={"type": "date"})}


class SaloonServicePackageForm(forms.Form):
    name = forms.CharField(max_length=150)
    service = forms.ModelChoiceField(queryset=SaloonService.objects.none())
    session_count = forms.IntegerField(min_value=1)
    price = forms.DecimalField(max_digits=10, decimal_places=2)
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = SaloonService.objects.for_company(company).filter(is_active=True)


class SaloonPackagePurchaseForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    package = forms.ModelChoiceField(queryset=SaloonServicePackage.objects.none())
    purchased_on = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none())
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
        self.fields["package"].queryset = SaloonServicePackage.objects.for_company(company).filter(is_active=True)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)


# ---------------- Beauty Parlour ----------------

class BeautyServiceForm(forms.Form):
    name = forms.CharField(max_length=150)
    duration_minutes = forms.IntegerField(min_value=1)
    price = forms.DecimalField(max_digits=10, decimal_places=2)


class BookBeautyAppointmentForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    service = forms.ModelChoiceField(queryset=BeautyService.objects.none())
    beautician = forms.ModelChoiceField(queryset=Employee.objects.none())
    scheduled_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    commission_rate_percent = forms.DecimalField(max_digits=5, decimal_places=2, required=False, initial=0, label="Beautician commission %")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
            self.fields["service"].queryset = BeautyService.objects.for_company(company).filter(is_active=True)
            self.fields["beautician"].queryset = Employee.objects.for_company(company).filter(is_active=True)


# ---------------- Medical Shop ----------------

class MedicineBatchForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    batch_number = forms.CharField(max_length=50)
    manufacturer = forms.CharField(max_length=150, required=False)
    expiry_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    received_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    purchase_price = forms.DecimalField(max_digits=10, decimal_places=2)
    selling_price = forms.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = forms.DecimalField(max_digits=10, decimal_places=2)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["product"].queryset = Product.objects.for_company(company)


class DispenseForm(forms.Form):
    quantity = forms.DecimalField(max_digits=10, decimal_places=2)
    sold_price = forms.DecimalField(max_digits=10, decimal_places=2)
    sold_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    prescription_reference = forms.CharField(max_length=100, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)


# ---------------- Protein Shop ----------------

class ProteinBatchForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    batch_number = forms.CharField(max_length=50)
    flavour = forms.CharField(max_length=100, required=False)
    weight_grams = forms.IntegerField(min_value=1, label="Pack size (grams)")
    expiry_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    received_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    purchase_price = forms.DecimalField(max_digits=10, decimal_places=2)
    selling_price = forms.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = forms.DecimalField(max_digits=10, decimal_places=2)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["product"].queryset = Product.objects.for_company(company)


class SellProteinForm(forms.Form):
    quantity = forms.DecimalField(max_digits=10, decimal_places=2)
    sold_price = forms.DecimalField(max_digits=10, decimal_places=2)
    sold_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)


# ---------------- Construction ----------------

class ProjectForm(forms.Form):
    name = forms.CharField(max_length=255)
    client = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    site_address = forms.CharField(widget=forms.Textarea, required=False)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), required=False)
    budget = forms.DecimalField(max_digits=14, decimal_places=2, initial=0)
    contract_value = forms.DecimalField(max_digits=14, decimal_places=2, initial=0)
    status = forms.ChoiceField(choices=[
        ("planning", "Planning"), ("active", "Active"), ("on_hold", "On Hold"),
        ("completed", "Completed"), ("cancelled", "Cancelled"),
    ], required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["client"].queryset = Customer.objects.for_company(company).filter(is_active=True)
            from apps.modules.catalog import business_profile
            profile = business_profile(company.business_type.code)
            self.fields["name"].label = profile.get("projects_label", "Project").rstrip("s") + " name"
            self.fields["site_address"].label = profile.get("location_label", "Location / Scope")


class ContractorForm(forms.ModelForm):
    class Meta:
        model = Contractor
        fields = ["name", "phone", "specialty"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            from apps.modules.catalog import business_profile
            provider = business_profile(company.business_type.code).get("provider_label", "Vendor")
            self.fields["name"].label = provider.rstrip("s") + " name"


class ProjectExpenseForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none())
    category = forms.ChoiceField(choices=ProjectExpense.CATEGORY)
    contractor = forms.ModelChoiceField(queryset=Contractor.objects.none(), required=False)
    amount = forms.DecimalField(max_digits=14, decimal_places=2)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    description = forms.CharField(max_length=255, required=False)
    payment_method = forms.ChoiceField(
        choices=[("cash", "Cash"), ("bank", "Bank")], initial="cash"
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["project"].queryset = Project.objects.for_company(company)
            self.fields["contractor"].queryset = Contractor.objects.for_company(company).filter(is_active=True)


class ProjectMilestoneForm(forms.ModelForm):
    class Meta:
        model = ProjectMilestone
        fields = ["name", "due_date", "amount", "status", "completion_percent", "notes"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}


class ProjectTaskForm(forms.ModelForm):
    class Meta:
        model = ProjectTask
        fields = ["milestone", "title", "assigned_to", "due_date", "status", "priority", "description"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, company=None, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["milestone"].queryset = ProjectMilestone.objects.for_company(company).filter(project=project)
        self.fields["assigned_to"].queryset = Employee.objects.for_company(company).filter(is_active=True)


class ProjectTimesheetForm(forms.ModelForm):
    class Meta:
        model = ProjectTimesheet
        fields = ["task", "employee", "date", "hours", "hourly_rate", "description"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
    def __init__(self, *args, company=None, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task"].queryset = ProjectTask.objects.for_company(company).filter(project=project)
        self.fields["employee"].queryset = Employee.objects.for_company(company).filter(is_active=True)

# ---------------- Generic Retail (Watch / Perfume / Book Store) ----------------

class RetailSaleForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    quantity = forms.DecimalField(max_digits=10, decimal_places=2, initial=1)
    unit_price = forms.DecimalField(max_digits=12, decimal_places=2, help_text="Defaults to the product's selling price if left as-is")
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)
            self.fields["product"].queryset = Product.objects.for_company(company).filter(is_active=True)

class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ["name"]
        labels = {"name": "Unit name (e.g. pcs, kg, meter, box)"}

# ---------------- Suppliers & Purchases ----------------

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "phone", "email", "address"]


class PurchaseForm(forms.Form):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none())
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none(), label="Branch/Warehouse", required=False)
    quantity = forms.DecimalField(max_digits=12, decimal_places=3, initial=1)
    unit_cost = forms.DecimalField(max_digits=12, decimal_places=2)
    bill_number = forms.CharField(max_length=30, required=False)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["supplier"].queryset = Supplier.objects.for_company(company).filter(is_active=True)
            self.fields["product"].queryset = Product.objects.for_company(company)
            self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)


class SupplierPaymentForm(forms.Form):
    purchase = forms.ModelChoiceField(queryset=Purchase.objects.none(), required=False, label="Against bill (optional)")
    amount = forms.DecimalField(max_digits=14, decimal_places=2)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    method = forms.ChoiceField(choices=[("cash", "Cash"), ("bank", "Bank")], initial="cash")

    def __init__(self, *args, company=None, supplier=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None and supplier is not None:
            self.fields["purchase"].queryset = Purchase.objects.for_company(company).filter(supplier=supplier)

class InvoiceLookupForm(forms.Form):
    invoice_number = forms.CharField(max_length=30, label="Invoice number (e.g. INV-000001)")


class SalesReturnForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    refund_method = forms.ChoiceField(choices=SalesReturn.REFUND_METHOD)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

# ---------------- Expenses ----------------

class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name"]


class ExpenseForm(forms.Form):
    category = forms.ModelChoiceField(queryset=ExpenseCategory.objects.none())
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    amount = forms.DecimalField(max_digits=14, decimal_places=2)
    description = forms.CharField(max_length=255, required=False)
    payment_method = forms.ChoiceField(
        choices=[("cash", "Cash"), ("card", "Card"), ("bank", "Bank")], initial="cash"
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["category"].queryset = ExpenseCategory.objects.for_company(company).order_by("name")

# ---------------- Staff & Roles (RBAC) ----------------

class InviteStaffForm(forms.Form):
    username = forms.CharField(max_length=150, label="Login username")
    email = forms.EmailField(label="Email")
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Login password")
    role = forms.ModelChoiceField(queryset=Role.objects.none())

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["role"].queryset = Role.objects.filter(company=company).order_by("name")

    def clean_username(self):
        from django.contrib.auth import get_user_model
        username = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        from django.contrib.auth import get_user_model
        email = self.cleaned_data["email"].strip()
        if get_user_model().objects.filter(email=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email


class ChangeMemberRoleForm(forms.Form):
    role = forms.ModelChoiceField(queryset=Role.objects.none())

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["role"].queryset = Role.objects.filter(company=company).order_by("name")


class CustomRoleForm(forms.Form):
    name = forms.CharField(max_length=50, label="Role name (e.g. Cashier)")

# ---------------- Coupons & Loyalty ----------------

class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ["code", "discount_type", "discount_value", "min_purchase", "max_discount", "start_date", "expiry_date", "usage_limit"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }


class RedeemPointsForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none())
    points = forms.IntegerField(min_value=1)
    reason = forms.CharField(max_length=150, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)

# ---------------- Settings ----------------

class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "registration_number", "vat_number", "country", "address", "phone", "email", "default_currency", "logo"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

# ---------------- Branches ----------------

class BranchForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["name", "address", "phone", "manager_name", "is_default"]

# ---------------- Import / Export ----------------

class ProductImportForm(forms.Form):
    csv_file = forms.FileField(label="CSV file")

# ---------------- Platform Admin ----------------

class EditUserCredentialsForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    new_password = forms.CharField(
        widget=forms.PasswordInput, required=False, min_length=8,
        label="New password (leave blank to keep current)",
    )

    def __init__(self, *args, user_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_instance = user_instance

    def clean_username(self):
        from django.contrib.auth import get_user_model
        username = self.cleaned_data["username"].strip()
        qs = get_user_model().objects.filter(username=username)
        if self._user_instance:
            qs = qs.exclude(id=self._user_instance.id)
        if qs.exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        from django.contrib.auth import get_user_model
        email = self.cleaned_data["email"].strip()
        qs = get_user_model().objects.filter(email=email)
        if self._user_instance:
            qs = qs.exclude(id=self._user_instance.id)
        if qs.exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ["name", "country", "currency", "price", "billing_period", "max_users", "max_warehouses", "max_invoices_per_month", "storage_limit_mb", "grace_period_days", "modules", "is_active"]


class PlatformModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["code", "name", "is_core"]
        help_texts = {
            "code": "Stable internal name, for example inventory or mobile_shop.",
            "is_core": "Core modules are enabled for every company and cannot be switched off.",
        }


class PaymentGatewaySettingsForm(forms.Form):
    stripe_enabled = forms.BooleanField(required=False, label="Enable Stripe")
    stripe_test_mode = forms.BooleanField(required=False, label="Stripe test mode")
    stripe_publishable_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    stripe_secret_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    stripe_webhook_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    clear_stripe_keys = forms.BooleanField(required=False, label="Remove saved Stripe keys")

    razorpay_enabled = forms.BooleanField(required=False, label="Enable Razorpay")
    razorpay_test_mode = forms.BooleanField(required=False, label="Razorpay test mode")
    razorpay_key_id = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    razorpay_key_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    razorpay_webhook_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False))
    clear_razorpay_keys = forms.BooleanField(required=False, label="Remove saved Razorpay keys")

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        if instance and not self.is_bound:
            self.initial.update({
                "stripe_enabled": instance.stripe_enabled,
                "stripe_test_mode": instance.stripe_test_mode,
                "razorpay_enabled": instance.razorpay_enabled,
                "razorpay_test_mode": instance.razorpay_test_mode,
            })
        for name in (
            "stripe_publishable_key", "stripe_secret_key", "stripe_webhook_secret",
            "razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret",
        ):
            self.fields[name].help_text = "Leave blank to keep the currently saved value."

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("stripe_enabled"):
            existing = self.instance and not cleaned.get("clear_stripe_keys") and self.instance.get_secret("stripe_secret_key")
            if not cleaned.get("stripe_secret_key") and not existing:
                self.add_error("stripe_secret_key", "A Stripe secret key is required when Stripe is enabled.")
        if cleaned.get("razorpay_enabled"):
            existing_id = self.instance and not cleaned.get("clear_razorpay_keys") and self.instance.get_secret("razorpay_key_id")
            existing_secret = self.instance and not cleaned.get("clear_razorpay_keys") and self.instance.get_secret("razorpay_key_secret")
            if not cleaned.get("razorpay_key_id") and not existing_id:
                self.add_error("razorpay_key_id", "A Razorpay key ID is required when Razorpay is enabled.")
            if not cleaned.get("razorpay_key_secret") and not existing_secret:
                self.add_error("razorpay_key_secret", "A Razorpay key secret is required when Razorpay is enabled.")
        return cleaned

    def save(self, user):
        obj = self.instance
        obj.stripe_enabled = self.cleaned_data["stripe_enabled"]
        obj.stripe_test_mode = self.cleaned_data["stripe_test_mode"]
        obj.razorpay_enabled = self.cleaned_data["razorpay_enabled"]
        obj.razorpay_test_mode = self.cleaned_data["razorpay_test_mode"]

        groups = {
            "stripe": ("stripe_publishable_key", "stripe_secret_key", "stripe_webhook_secret"),
            "razorpay": ("razorpay_key_id", "razorpay_key_secret", "razorpay_webhook_secret"),
        }
        for provider, names in groups.items():
            if self.cleaned_data.get(f"clear_{provider}_keys"):
                for name in names:
                    obj.set_secret(name, "")
            else:
                for name in names:
                    value = self.cleaned_data.get(name)
                    if value:
                        obj.set_secret(name, value.strip())
        obj.updated_by = user
        obj.save()
        return obj


class PlatformBusinessTypeForm(forms.ModelForm):
    default_modules = forms.ModelMultipleChoiceField(
        queryset=Module.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Enabled automatically for new companies of this business type.",
    )

    class Meta:
        model = BusinessType
        fields = ["code", "name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_modules"].queryset = Module.objects.all().order_by("name")
        if self.instance and self.instance.pk:
            self.fields["default_modules"].initial = Module.objects.filter(
                businesstypedefaultmodule__business_type=self.instance
            )


class PlatformSupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ["status", "priority", "assigned_to"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        self.fields["assigned_to"].queryset = get_user_model().objects.filter(
            is_platform_admin=True
        ).order_by("email", "username")


class BillingPaymentForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2)
    method = forms.ChoiceField(choices=[("bank", "Bank Transfer"), ("cash", "Cash"), ("other", "Other")])
    reference = forms.CharField(max_length=100, label="Transaction / reference number", required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)


class DiningAreaForm(forms.ModelForm):
    class Meta:
        model = DiningArea
        fields = ["name", "is_active"]


class DiningTableForm(forms.ModelForm):
    class Meta:
        model = DiningTable
        fields = ["area", "name", "capacity", "status", "is_active"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["area"].queryset = DiningArea.objects.for_company(company).filter(is_active=True)


class RestaurantOrderForm(forms.Form):
    channel = forms.ChoiceField(choices=RestaurantOrder.CHANNELS)
    table = forms.ModelChoiceField(queryset=DiningTable.objects.none(), required=False)
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    delivery_address = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    delivery_phone = forms.CharField(max_length=30, required=False)
    guests = forms.IntegerField(min_value=0, max_value=500, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = DiningTable.objects.for_company(company).filter(is_active=True)
        self.fields["customer"].queryset = Customer.objects.for_company(company).filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("channel") == "dine_in" and not cleaned.get("table"):
            self.add_error("table", "Select a table for dine-in.")
        if cleaned.get("channel") == "delivery" and not cleaned.get("delivery_address"):
            self.add_error("delivery_address", "Enter the delivery address.")
        return cleaned


class RestaurantOrderLineForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none())
    quantity = forms.DecimalField(max_digits=10, decimal_places=3, min_value=0.001, initial=1)
    unit_price = forms.DecimalField(max_digits=12, decimal_places=2, required=False)
    modifiers = forms.ModelMultipleChoiceField(queryset=MenuModifier.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)
    notes = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.for_company(company).filter(is_active=True)
        self.fields["modifiers"].queryset = MenuModifier.objects.for_company(company).filter(is_active=True)


class RestaurantSettleForm(forms.Form):
    warehouse = forms.ModelChoiceField(queryset=Warehouse.objects.none())
    cash = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=0)
    card = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=0)
    bank = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=0)
    service_charge = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=0)
    tip_amount = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=0)
    discount_amount = forms.DecimalField(max_digits=12, decimal_places=2, required=False, initial=0)

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)


class RestaurantShiftOpenForm(forms.Form):
    opening_cash = forms.DecimalField(max_digits=12, decimal_places=2, initial=0)


class RestaurantShiftCloseForm(forms.Form):
    actual_cash = forms.DecimalField(max_digits=12, decimal_places=2)


class MenuModifierForm(forms.ModelForm):
    class Meta:
        model = MenuModifier
        fields = ["name", "price_delta", "is_active"]


class RestaurantMenuItemForm(forms.ModelForm):
    sku = forms.CharField(max_length=50, label="Menu code / SKU")
    name = forms.CharField(max_length=255, label="Dish name")
    category = forms.ModelChoiceField(queryset=ProductCategory.objects.none(), required=False)
    selling_price = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0)

    class Meta:
        model = RestaurantMenuItem
        fields = [
            "sku", "name", "category", "selling_price", "description", "image",
            "preparation_minutes", "spice_level", "is_vegetarian", "is_featured",
            "is_available", "available_from", "available_until", "modifier_groups", "sort_order",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Short menu description"}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
            "available_from": forms.TimeInput(attrs={"type": "time"}),
            "available_until": forms.TimeInput(attrs={"type": "time"}),
            "modifier_groups": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.fields["category"].queryset = ProductCategory.objects.for_company(company).order_by("name")
        self.fields["modifier_groups"].queryset = MenuModifierGroup.objects.for_company(company).filter(is_active=True)
        if self.instance and self.instance.pk:
            product = self.instance.product
            self.fields["sku"].initial = product.sku
            self.fields["name"].initial = product.name
            self.fields["category"].initial = product.category_id
            self.fields["selling_price"].initial = product.selling_price

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip()
        qs = Product.objects.for_company(self.company).filter(sku=sku)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.product_id)
        if qs.exists():
            raise forms.ValidationError("This menu code / SKU is already in use.")
        return sku

    def save(self, commit=True):
        menu_item = super().save(commit=False)
        product = menu_item.product if menu_item.pk else Product(company=self.company)
        unit, _ = Unit.objects.get_or_create(company=self.company, name="piece")
        product.sku = self.cleaned_data["sku"]
        product.name = self.cleaned_data["name"]
        product.category = self.cleaned_data.get("category")
        product.unit = unit
        product.selling_price = self.cleaned_data["selling_price"]
        product.is_stock_tracked = False
        product.tracking_type = "none"
        product.is_active = True
        if commit:
            product.save()
            menu_item.product = product
            menu_item.company = self.company
            menu_item.save()
            self._save_m2m()
        return menu_item


class RecipeIngredientForm(forms.ModelForm):
    class Meta:
        model = RecipeIngredient
        fields = ["menu_product", "ingredient_product", "quantity"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.objects.for_company(company).filter(is_active=True)
        self.fields["menu_product"].queryset = products.filter(is_stock_tracked=False)
        self.fields["ingredient_product"].queryset = products.filter(is_stock_tracked=True)


class MenuModifierGroupForm(forms.ModelForm):
    class Meta:
        model = MenuModifierGroup
        fields = ["name", "is_required", "min_selections", "max_selections", "is_active"]

    def clean(self):
        data = super().clean()
        if data.get("max_selections", 0) < data.get("min_selections", 0):
            self.add_error("max_selections", "Maximum selections cannot be lower than minimum selections.")
        return data


class MenuModifierOptionForm(forms.ModelForm):
    class Meta:
        model = MenuModifierOption
        fields = ["group", "modifier", "sort_order"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = MenuModifierGroup.objects.for_company(company).filter(is_active=True)
        self.fields["modifier"].queryset = MenuModifier.objects.for_company(company).filter(is_active=True)


class KitchenStationForm(forms.ModelForm):
    class Meta:
        model = KitchenStation
        fields = ["name", "categories", "colour", "is_active"]
        widgets = {"categories": forms.CheckboxSelectMultiple, "colour": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categories"].queryset = ProductCategory.objects.for_company(company).order_by("name")


class TableReservationForm(forms.ModelForm):
    class Meta:
        model = TableReservation
        fields = ["customer_name", "phone", "reservation_at", "guest_count", "table", "status", "notes"]
        widgets = {"reservation_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["table"].queryset = DiningTable.objects.for_company(company).filter(is_active=True)


class FoodWasteForm(forms.ModelForm):
    class Meta:
        model = FoodWaste
        fields = ["ingredient", "warehouse", "quantity", "reason", "notes"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ingredient"].queryset = Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=True)
        self.fields["warehouse"].queryset = Warehouse.objects.for_company(company).filter(is_active=True)


class RestaurantProfileForm(forms.ModelForm):
    class Meta:
        model = RestaurantProfile
        fields = ["tagline", "opening_hours", "delivery_minimum", "delivery_charge", "qr_ordering_enabled",
                  "service_charge_percent", "tax_percent"]


class RestaurantComboForm(forms.ModelForm):
    class Meta:
        model = RestaurantCombo
        fields = ["name", "billing_product", "is_active"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["billing_product"].queryset = Product.objects.for_company(company).filter(is_active=True, is_stock_tracked=False)


class RestaurantComboItemForm(forms.ModelForm):
    class Meta:
        model = RestaurantComboItem
        fields = ["combo", "product", "quantity"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["combo"].queryset = RestaurantCombo.objects.for_company(company).filter(is_active=True)
        self.fields["product"].queryset = Product.objects.for_company(company).filter(is_active=True)


class DeliveryIntegrationForm(forms.ModelForm):
    api_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="Leave blank to keep the saved key.")
    api_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="Leave blank to keep the saved secret.")
    webhook_secret = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False), help_text="Used to verify webhook signatures.")
    clear_credentials = forms.BooleanField(required=False)

    class Meta:
        model = DeliveryIntegration
        fields = ["provider", "display_name", "store_id", "api_base_url", "is_enabled", "test_mode", "auto_accept_orders", "commission_percent"]

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)
        self.integration = instance

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_enabled"):
            existing_key = self.integration and not cleaned.get("clear_credentials") and self.integration.api_key_ciphertext
            existing_webhook = self.integration and not cleaned.get("clear_credentials") and self.integration.webhook_secret_ciphertext
            if not cleaned.get("api_key") and not existing_key:
                self.add_error("api_key", "API key is required when enabled.")
            if not cleaned.get("webhook_secret") and not existing_webhook:
                self.add_error("webhook_secret", "Webhook secret is required when enabled.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("clear_credentials"):
            for name in ("api_key", "api_secret", "webhook_secret"): obj.set_secret(name, "")
        else:
            for name in ("api_key", "api_secret", "webhook_secret"):
                if self.cleaned_data.get(name): obj.set_secret(name, self.cleaned_data[name].strip())
        if commit: obj.save()
        return obj

class ClientCommercialProfileForm(forms.ModelForm):
    class Meta:
        from apps.subscriptions.models import ClientCommercialProfile
        model = ClientCommercialProfile
        fields = ['max_branches','max_pos_terminals','api_calls_per_month','custom_monthly_price','reseller_name','white_label_name','custom_domain','admin_notes']
        widgets = {'admin_notes': forms.Textarea(attrs={'rows':4})}
