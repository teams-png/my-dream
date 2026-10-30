"""Wash bay: type a plate (new owner made on the spot, same plate found again), queue → washing → done & paid, WhatsApp."""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.industry.tests.test_jobs import _clean_cache, _garage  # noqa: F401
from apps.sales.models import CustomerPayment
from apps.verticals.vehicle_wash.models import Vehicle, WashOrder
from apps.verticals.vehicle_wash.services import create_wash_package

pytestmark = pytest.mark.django_db


def test_queue_wash_and_pay():
    company, owner, staff = _garage("wash1@t.qa", kind="vehicle_wash")
    pkg = create_wash_package(company=company, name="Foam wash", vehicle_type="car", price=Decimal("400"))
    when = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
    assert owner.get(reverse("webapp:wash_order_book")).status_code == 200
    r = owner.post(reverse("webapp:wash_order_book"), {
        "vehicle_number": "kl 11 ab 1234", "owner_name": "Shameer", "phone": "+974 5555 7711", "vehicle_type": "car",
        "make_model": "Maruti Swift", "package": pkg.id, "staff": staff.id, "scheduled_at": when, "price": ""})
    assert r.status_code == 302
    v = Vehicle.objects.get(company=company)
    assert v.vehicle_number == "KL 11 AB 1234" and v.make == "Maruti" and v.model == "Swift" and v.customer.name == "Shameer"
    owner.post(reverse("webapp:wash_order_book"), {"vehicle_number": "KL11AB1234", "vehicle_type": "car", "package": pkg.id,
                                                   "scheduled_at": when, "price": ""})
    assert Vehicle.objects.filter(company=company).count() == 1 and WashOrder.objects.filter(company=company).count() == 2
    first, second = WashOrder.objects.filter(company=company).order_by("id")
    assert owner.get(reverse("webapp:wash_order_start", args=[first.id])).status_code == 405
    owner.post(reverse("webapp:wash_order_start", args=[first.id]))
    bay = owner.get(reverse("webapp:wash_order_list")).content.decode()
    assert "KL 11 AB 1234" in bay and "Washing" in bay and "wa.me/" in bay and "is washed and ready" in bay.replace("%20", " ")
    owner.post(reverse("webapp:wash_order_complete", args=[first.id]), {"method": "bank"})
    first.refresh_from_db()
    assert first.status == "completed" and first.sales_invoice.status == "paid"
    assert CustomerPayment.objects.get(invoice=first.sales_invoice).method == "bank"
    assert first.sales_invoice.served_by_id == staff.id
    book = owner.get(reverse("webapp:wash_order_book")).content.decode()
    assert "KL11AB1234" in book and "Shameer" in book
    owner.post(reverse("webapp:wash_order_cancel", args=[second.id]))
    second.refresh_from_db()
    assert second.status == "cancelled"
    assert "Foam wash" in owner.get(reverse("webapp:wash_order_list") + "?show=all").content.decode()
