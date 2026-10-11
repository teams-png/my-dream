"""Sports shop: size charts (staff and website) and equipment rental with deposit, late days and the bill."""
import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.webapp.tests.test_expiry_shops import _shop

pytestmark = pytest.mark.django_db


def test_size_chart_and_rental_out_and_back():
    from apps.inventory.models import ProductCategory
    from apps.verticals.sports_shop.models import Rental, RentalItem, SizeChart
    company, user, c = _shop("sports_shop")
    cat = ProductCategory.objects.create(company=company, name="Jerseys")
    c.post(reverse("webapp:size_charts"), {"name": "Football jerseys", "category": cat.id,
                                            "table": "Size, Chest (cm)\nS, 88–92\nM, 96–100", "note": "Take the bigger one"})
    chart = SizeChart.objects.get(company=company)
    assert chart.rows == [["Size", "Chest (cm)"], ["S", "88–92"], ["M", "96–100"]]
    page = c.get(reverse("webapp:size_charts")).content.decode()
    assert "<th>Chest (cm)</th>" in page and "96–100" in page
    assert "Size charts" in c.get(reverse("webapp:dashboard")).content.decode()

    c.post(reverse("webapp:sports_rentals"), {"name": "Mountain bike", "rate_per_day": "40", "deposit": "200", "quantity_owned": "2"})
    bike = RentalItem.objects.get(company=company)
    r = c.post(reverse("webapp:sports_rental_add"), {"new_name": "Sara", "new_phone": "5555 0001", f"qty_{bike.id}": "3",
                                                     "due_back": (timezone.localdate() + datetime.timedelta(days=1)).isoformat()})
    assert not Rental.objects.exists()  # only 2 bikes
    r = c.post(reverse("webapp:sports_rental_add"), {"new_name": "Sara", "new_phone": "5555 0001", f"qty_{bike.id}": "2",
                                                     "id_document": "QID 123",
                                                     "due_back": (timezone.localdate() + datetime.timedelta(days=1)).isoformat()})
    rental = Rental.objects.get(company=company)
    assert r.status_code == 302 and rental.deposit == 400 and rental.number.startswith("RNT-")
    listing = c.get(reverse("webapp:sports_rentals")).content.decode()
    assert "0/2 free" in listing and "Sara" in listing
    detail = c.get(reverse("webapp:sports_rental_detail", args=[rental.id])).content.decode()
    assert "Rental agreement" in detail and "wa.me/974" in detail

    Rental.objects.filter(id=rental.id).update(out_at=timezone.now() - datetime.timedelta(days=2, hours=3))
    c.post(reverse("webapp:sports_rental_return", args=[rental.id]), {"damage_charge": "50", "return_note": "brake cable"})
    rental.refresh_from_db()
    assert rental.status == "returned" and rental.days_charged == 3
    assert rental.charge == Decimal("40") * 2 * 3 + 50 == rental.invoice.total
    assert rental.invoice.amount_paid == min(rental.deposit, rental.invoice.total)  # paid from the deposit
    assert "2/2 free" in c.get(reverse("webapp:sports_rentals")).content.decode()


def test_size_chart_on_website_product_page():
    from apps.industry import site_builder, website_kit
    from apps.inventory.models import Product, ProductCategory, Unit
    from apps.verticals.sports_shop.models import SizeChart
    company, user, c = _shop("sports_shop")
    cat = ProductCategory.objects.create(company=company, name="Jerseys")
    unit = Unit.objects.filter(company=company).first() or Unit.objects.create(company=company, name="pcs")
    p = Product.objects.create(company=company, sku="J1", name="Home jersey", category=cat, unit=unit, selling_price=99,
                               is_stock_tracked=False, tracking_type="none")
    SizeChart.objects.create(company=company, name="Jerseys", category=cat, table="Size, Chest\nM, 100")
    d = site_builder.design_for(company)
    d.enabled = d.published = True
    d.save()
    kit = website_kit.kit_for(company)
    page = c.get(f"/site/{kit.public_id}/shop/{p.id}/").content.decode()
    assert "Size chart" in page and "<td>100</td>" in page
