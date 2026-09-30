"""Weighing-scale barcode settings for shops that sell by weight."""
import re

from django import forms
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.industry.models import ScaleSettings
from apps.inventory.models import Product

from .industry_access import require_industry


class ScaleSettingsForm(forms.ModelForm):
    class Meta:
        model = ScaleSettings
        fields = ["prefixes", "code_digits", "value_type", "value_decimals"]

    def clean_prefixes(self):
        parts = [p.strip() for p in self.cleaned_data["prefixes"].split(",") if p.strip()]
        if not parts or any(not re.fullmatch(r"\d{1,3}", p) for p in parts):
            raise forms.ValidationError(_("Use 1–3 digit prefixes separated by commas, e.g. 20,21,22."))
        return ",".join(parts)

    def clean(self):
        cleaned = super().clean()
        longest = max((len(p) for p in (cleaned.get("prefixes") or "").split(",") if p), default=2)
        digits = cleaned.get("code_digits") or 0
        if not 2 <= digits <= 7 or longest + digits > 9:
            raise forms.ValidationError(_("Prefix and item code must leave at least 3 digits for the value."))
        if cleaned.get("value_decimals") is not None and cleaned["value_decimals"] > 3:
            self.add_error("value_decimals", _("At most 3 decimals."))
        return cleaned


@require_industry("weighed")
def scale_settings(request):
    company = request.company
    settings_obj = ScaleSettings.load(company)
    form = ScaleSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Scale settings saved."))
        return redirect("webapp:scale_settings")
    weighed = [p for p in Product.objects.for_company(company).filter(is_active=True).order_by("name")
               if (p.attributes or {}).get("sold_by_weight")]
    return render(request, "webapp/industry/scale_settings.html", {
        "form": form, "weighed": weighed, "example": _example(settings_obj)})


def _example(cfg):
    prefix = (cfg.prefixes.split(",") or ["21"])[0]
    code = "123".zfill(cfg.code_digits)
    value_digits = 12 - len(prefix) - cfg.code_digits
    value = str(1250 if cfg.value_type == "weight" else 1875).zfill(value_digits)[-value_digits:]
    body = prefix + code + value
    check = (10 - sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body)) % 10) % 10
    shown = int(value) / (10 ** cfg.value_decimals)
    return {"barcode": body + str(check), "prefix": prefix, "code": code, "value": value, "check": check,
            "meaning": (f"{shown:.3f} kg" if cfg.value_type == "weight" else f"{shown:.2f}")}
