"""Every form gets sample placeholders and "Select …" dropdowns; category / brand can be added inline."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.common import form_hints
from apps.inventory.models import Brand, Product, ProductCategory, Unit
from apps.tenants.services import create_company_with_owner

pytestmark = pytest.mark.django_db


def _company(code):
    from django.core.management import call_command
    call_command("seed_platform")
    user = get_user_model().objects.create_user(username=f"o-{code}", email=f"o-{code}@t.qa", password="Pass-12345!")
    from apps.modules.models import BusinessType
    company = create_company_with_owner(user=user, name=f"Biz {code}", slug=f"biz-{code}", business_type=BusinessType.objects.get(code=code))
    return company, user


def test_samples_follow_the_business_type():
    from apps.webapp.forms import ProductForm
    company, _ = _company("restaurant")
    token = form_hints.activate(company)
    try:
        form = ProductForm(company=company)
    finally:
        form_hints.reset(token)
    assert "Chicken Biryani" in form.fields["name"].widget.attrs["placeholder"]
    assert "Biryani" in form.fields["new_category"].widget.attrs["placeholder"]
    assert form.fields["category"].empty_label == "Select category"


def test_new_category_and_brand_are_created_from_the_product_form():
    from apps.webapp.forms import ProductForm
    company, _ = _company("mobile_shop")
    unit = Unit.objects.create(company=company, name="pcs")
    form = ProductForm({"sku": "SAM-1", "name": "Galaxy A15", "unit": unit.id, "cost_price": "500", "selling_price": "650",
                        "reorder_level": "2", "new_category": "Mobiles", "new_brand": "Samsung"}, company=company)
    assert form.is_valid(), form.errors
    product = form.save(commit=False)
    product.company = company
    product.save()
    assert product.category.name == "Mobiles" and product.brand.name == "Samsung"
    # typing an existing name re-uses it
    form = ProductForm({"sku": "SAM-2", "name": "Galaxy A25", "unit": unit.id, "cost_price": "600", "selling_price": "750",
                        "reorder_level": "2", "new_category": "mobiles"}, company=company)
    assert form.is_valid()
    assert ProductCategory.objects.for_company(company).count() == 1 and Brand.objects.for_company(company).count() == 1


def test_menu_item_page_and_inline_category(client):
    company, user = _company("restaurant")
    client.force_login(user)
    page = client.get(reverse("webapp:restaurant_menu_item_add")).content.decode()
    assert "Dish details" in page and "e.g. Chicken Biryani" in page and 'name="new_category"' in page
    response = client.post(reverse("webapp:restaurant_menu_item_add"), {
        "sku": "BIR-001", "name": "Chicken Biryani", "selling_price": "28", "new_category": "Biryani",
        "preparation_minutes": "15", "spice_level": "none", "is_available": "on", "sort_order": "0"})
    assert response.status_code == 302
    assert Product.objects.for_company(company).get(sku="BIR-001").category.name == "Biryani"


def test_dates_and_times_get_pickers_and_years_an_example():
    from django import forms

    class Sample(forms.Form):
        joined = forms.DateField()
        opens = forms.TimeField()
        starts = forms.DateTimeField()
        model_year = forms.IntegerField()

    html = str(Sample().as_p())
    assert 'type="date"' in html and 'type="time"' in html and 'type="datetime-local"' in html
    assert 'name="model_year" placeholder="' in html
    form = Sample({"joined": "2026-10-04", "opens": "09:30", "starts": "2026-10-04T09:30", "model_year": "2024"})
    assert form.is_valid(), form.errors


def test_page_ships_examples_for_hand_written_forms(client):
    company, user = _company("jewelry_shop")
    client.force_login(user)
    page = client.get(reverse("webapp:branch_add")).content.decode()
    assert 'id="bp-form-samples"' in page and "form-hints.js" in page
    assert "Main branch" in page and "22K gold bangle" in page


def test_next_parameter_never_leaves_the_site(rf):
    from apps.common.safe_redirect import safe_next
    for bad in ("https://evil.example/", "//evil.example/x", "/\\evil.example", "javascript:alert(1)"):
        assert safe_next(rf.post("/", {"next": bad}), "/fallback/") == "/fallback/"
    assert safe_next(rf.post("/", {"next": "/restaurant/setup/"}), "/fallback/") == "/restaurant/setup/"


def test_script_json_cannot_close_a_script_tag():
    import json
    from apps.common.safe_json import script_json
    value = script_json({"name": "</script><script>alert(1)</script>"})
    assert "</script>" not in value and json.loads(value)["name"].startswith("</script>")
