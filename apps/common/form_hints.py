"""
Friendly forms everywhere: every text / number box gets an example placeholder ("e.g. Chicken Biryani")
that suits the business type, and empty dropdowns read "Select category" instead of "---------".
Applied to every Django form from CommonConfig.ready(); a placeholder a form sets itself always wins.
"""
from contextvars import ContextVar

from django import forms
from django.utils.translation import gettext as _

_company = ContextVar("bookpilot_form_company", default=None)

BLANK = "---------"

FAMILIES = {
    "restaurant": {"restaurant", "cafe_juice_shop", "catering_company", "bakery", "cloud_kitchen", "food_truck"},
    "beauty": {"saloon", "beauty_parlour", "spa", "barber_shop", "nail_studio"},
    "mobile": {"mobile_shop", "electronics_shop", "computer_shop"},
    "fashion": {"clothing_store", "ladies_fashion_boutique", "textile", "tailoring", "abaya_shop", "shoe_store"},
    "grocery": {"grocery", "supermarket", "fresh_food_retail", "general_retail", "retail_shop", "mini_market"},
    "pharmacy": {"medical_shop", "pharmacy", "protein_shop"},
}

# product, category, brand, sku, description
PRODUCT_SAMPLES = {
    "restaurant": ("Chicken Biryani", "Biryani", "House special", "BIR-001",
                   "Fragrant basmati rice slow-cooked with tender chicken and spices"),
    "beauty": ("Keratin hair treatment", "Hair care", "L'Oréal", "HC-001", "Smooth, frizz-free hair for up to 3 months"),
    "mobile": ("Samsung Galaxy A15 128GB", "Mobiles", "Samsung", "SAM-A15-128", "6.5\" display, 50MP camera, 5000 mAh"),
    "fashion": ("Men's cotton kandura", "Kandura", "Al Jazeera", "KAN-001", "Soft cotton, regular fit"),
    "grocery": ("Almarai full fat milk 1L", "Dairy", "Almarai", "6281007000017", "Fresh full-cream milk"),
    "pharmacy": ("Panadol Extra 24 tablets", "Pain relief", "GSK", "PAN-24", "For headache and fever"),
    "default": ("Product name", "General", "Brand name", "SKU-1001", "Short description customers will see"),
}

FIELD_SAMPLES = {
    "email": "name@example.com", "contact_email": "name@example.com",
    "phone": "+974 5555 1234", "mobile": "+974 5555 1234", "whatsapp": "+974 5555 1234", "contact_phone": "+974 5555 1234",
    "alternate_phone": "+974 6666 4321",
    "address": "Building 12, Street 340, Al Sadd, Doha", "billing_address": "Building 12, Street 340, Al Sadd, Doha",
    "shipping_address": "Building 12, Street 340, Al Sadd, Doha", "city": "Doha", "country": "Qatar", "area": "Al Sadd",
    "vat_number": "300123456700003", "tax_number": "300123456700003", "trn": "300123456700003",
    "registration_number": "CR 123456", "cr_number": "CR 123456", "licence": "MOL-12345",
    "website": "https://www.example.com", "url": "https://www.example.com", "map_url": "https://maps.app.goo.gl/…",
    "instagram": "@yourbusiness", "facebook": "yourbusiness", "tiktok": "@yourbusiness",
    "first_name": "Ahmed", "last_name": "Al-Kuwari", "full_name": "Ahmed Al-Kuwari", "contact_name": "Ahmed Al-Kuwari",
    "customer_name": "Ahmed Al-Kuwari", "contact_person": "Ahmed Al-Kuwari", "guest_name": "Ahmed Al-Kuwari",
    "company_name": "Al Noor Trading WLL", "business_name": "Al Noor Trading WLL",
    "bank_name": "QNB", "iban": "QA58 DOHB 0000 1234 5678 90AB CDEF G", "account_number": "0123456789",
    "swift": "QNBAQAQA", "cheque_number": "000123", "reference": "INV-2026-0001", "invoice_number": "INV-2026-0001",
    "barcode": "6281000000017", "model_number": "SM-A155F", "serial_number": "R58N12ABCDE", "imei": "356789012345678",
    "size": "M / 42 / 500 ml", "colour": "Black", "color": "Black", "material": "Cotton", "design": "Round neck",
    "notes": "Any extra details", "note": "Any extra details", "remarks": "Any extra details",
    "passport_number": "N1234567", "qid": "28435612345", "nationality": "Indian", "position": "Sales executive",
    "designation": "Sales executive", "job_title": "Sales executive", "department": "Sales",
    "plate_number": "123456", "vehicle_number": "123456", "room_number": "101", "table_number": "T1",
    "opening_hours": "Sat–Thu 10am–11pm\nFri 1pm–11pm",
}

NUMBER_SAMPLES = {
    "selling_price": "25.00", "price": "25.00", "cost_price": "15.00", "unit_price": "25.00", "rate": "150.00",
    "fee": "500.00", "amount": "100.00", "salary": "4500.00", "basic_salary": "4500.00", "discount_value": "10",
    "reorder_level": "10", "quantity": "1", "qty": "1", "capacity": "4", "seats": "4", "guest_count": "2",
    "preparation_minutes": "15", "duration_minutes": "30", "sort_order": "0", "vacancies": "5",
}


def activate(company):
    return _company.set(company)


def reset(token):
    _company.reset(token)


def family():
    company = _company.get()
    if company is None:
        return "default"
    try:
        code = company.business_type.code
    except Exception:
        return "default"
    for name, codes in FAMILIES.items():
        if code in codes:
            return name
    return "default"


def _model_name(form):
    meta = getattr(form, "_meta", None)
    model = getattr(meta, "model", None)
    return model.__name__.lower() if model else ""


def sample_for(form, name):
    model = _model_name(form)
    product, category, brand, sku, description = PRODUCT_SAMPLES[family()]
    if name in ("new_category", "category_name") or (model == "productcategory" and name == "name"):
        return category
    if name in ("new_brand", "brand_name") or (model == "brand" and name == "name"):
        return brand
    if model in ("product", "restaurantmenuitem") or "product" in type(form).__name__.lower():
        if name in ("name", "product_name"):
            return product
        if name == "sku":
            return sku
        if name == "description":
            return description
    if model == "customer" and name == "name":
        return "Ahmed Al-Kuwari"
    if model == "supplier" and name == "name":
        return "Al Meera Wholesale"
    if model in ("employee", "candidate") and name == "name":
        return "Ahmed Al-Kuwari"
    return FIELD_SAMPLES.get(name)


TEXT_TYPES = {"text", "email", "url", "tel", "search"}


def apply(form):
    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(field, forms.ModelChoiceField) and field.empty_label == BLANK:
            field.empty_label = _("Select %(label)s") % {"label": str(field.label or name.replace("_", " ")).lower()}
            continue
        if isinstance(field, forms.ChoiceField) and not isinstance(field, forms.ModelChoiceField):
            choices = list(field.choices)
            if choices and choices[0][0] in ("", None) and choices[0][1] == BLANK:
                choices[0] = ("", _("Select…"))
                field.choices = choices
            continue
        if widget.attrs.get("placeholder") or getattr(widget, "is_hidden", False):
            continue
        input_type = getattr(widget, "input_type", None)
        if isinstance(widget, forms.Textarea) or input_type in TEXT_TYPES:
            sample = sample_for(form, name)
            if sample:
                widget.attrs["placeholder"] = sample if "\n" in sample else _("e.g. %(sample)s") % {"sample": sample}
        elif input_type == "number":
            sample = NUMBER_SAMPLES.get(name)
            if sample:
                widget.attrs["placeholder"] = sample


def install():
    original = forms.BaseForm.__init__
    if getattr(original, "_bookpilot_hints", False):
        return

    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        try:
            apply(self)
        except Exception:  # hints are cosmetic; never break a form
            pass

    __init__._bookpilot_hints = True
    forms.BaseForm.__init__ = __init__
