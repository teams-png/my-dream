"""
Friendly forms everywhere: every text / number box gets an example placeholder ("e.g. Chicken Biryani")
that suits the business type, and empty dropdowns read "Select category" instead of "---------".
Applied to every Django form from CommonConfig.ready(); a placeholder a form sets itself always wins.
"""
from contextvars import ContextVar

from django import forms
from django.utils.translation import gettext as _

from .form_samples import FAMILIES, FIELD_SAMPLES, NAME_BY_PATH, NUMBER_SAMPLES, PRODUCT_SAMPLES

_context = ContextVar("bookpilot_form_context", default=(None, ""))

BLANK = "---------"


def activate(company, path=""):
    return _context.set((company, path or ""))


def reset(token):
    _context.reset(token)


def family():
    company = _context.get()[0]
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


def name_for_path(path=None):
    """Example for a plain "name" box, from the page it is on (branch, room, course, …)."""
    path = _context.get()[1] if path is None else path
    for prefix, sample in NAME_BY_PATH:
        if path.startswith(prefix):
            if sample is None:  # categories / brands / units pages use the business's own examples
                product, category, brand, *_ = PRODUCT_SAMPLES[family()]
                return brand if "brand" in prefix else category
            return sample
    return None


def client_samples():
    """Everything the browser-side helper needs to add examples to hand-written forms."""
    product, category, brand, sku, description = PRODUCT_SAMPLES[family()]
    fields = {**FIELD_SAMPLES, "product_name": product, "new_category": category, "new_brand": brand, "sku": sku}
    name = name_for_path()
    if name:
        fields["name"] = name
    return {"prefix": _("e.g. %(sample)s"), "fields": fields, "numbers": NUMBER_SAMPLES}


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
    if name == "name":
        return name_for_path()
    return FIELD_SAMPLES.get(name)


TEXT_TYPES = {"text", "email", "url", "tel", "search"}


YEAR_NAMES = ("year", "model_year", "manufacture_year", "academic_year", "fiscal_year", "year_built")


def _pickers(field):
    """Plain text date / time boxes become the phone's and browser's own calendar and clock pickers."""
    widget = field.widget
    if getattr(widget, "input_type", None) != "text" or isinstance(widget, forms.SplitDateTimeWidget):
        return
    if isinstance(field, forms.DateTimeField) and isinstance(widget, forms.DateTimeInput):
        widget.input_type, widget.format = "datetime-local", "%Y-%m-%dT%H:%M"
    elif isinstance(field, forms.DateField) and isinstance(widget, forms.DateInput):
        widget.input_type, widget.format = "date", "%Y-%m-%d"
    elif isinstance(field, forms.TimeField) and isinstance(widget, forms.TimeInput):
        widget.input_type, widget.format = "time", "%H:%M"


def apply(form):
    from django.utils import timezone
    for name, field in form.fields.items():
        widget = field.widget
        _pickers(field)
        if name in YEAR_NAMES or name.endswith("_year"):
            widget.attrs.setdefault("placeholder", str(timezone.localdate().year))
            if isinstance(field, forms.IntegerField):
                widget.attrs.setdefault("min", 1900)
                widget.attrs.setdefault("max", timezone.localdate().year + 5)
            continue
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
