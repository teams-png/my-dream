"""Quick add: a customer / supplier is added in a popup from another form and handed back to that form."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.customers.models import Customer
from apps.suppliers.models import Supplier

pytestmark = pytest.mark.django_db


def test_add_customer_and_supplier_in_the_popup(tenant_a, tenant_a_owner):
    c = Client()
    c.force_login(tenant_a_owner)
    page = c.get(reverse("webapp:dashboard")).content.decode()
    assert "js/quick-add.js" in page and reverse("webapp:customer_add") in page

    url = reverse("webapp:customer_add") + "?popup=1"
    form = c.get(url)
    assert form.status_code == 200 and form["X-Frame-Options"] == "SAMEORIGIN"
    assert 'class="bp-popup"' in form.content.decode()
    done = c.post(url, {"name": "Popup Customer", "phone": "5551", "email": "", "address": "",
                        "opening_balance": "0", "credit_limit": "0", "payment_terms_days": "0"})
    if done.status_code != 200 or "bp-quick-added" not in done.content.decode():
        pytest.fail(done.content.decode()[:3000])
    customer = Customer.objects.get(company=tenant_a, name="Popup Customer")
    assert f"{customer.id}" in done.content.decode()

    done = c.post(reverse("webapp:supplier_add") + "?popup=1", {"name": "Popup Supplier", "phone": "", "email": "",
                                                               "address": "", "opening_balance": "0"})
    assert "bp-quick-added" in done.content.decode() and Supplier.objects.filter(name="Popup Supplier").exists()

    # without ?popup the old flow is unchanged
    assert c.post(reverse("webapp:customer_add"), {"name": "Normal", "opening_balance": "0", "credit_limit": "0",
                                                   "payment_terms_days": "0"}).status_code == 302
