"""Job card records per business kind: clinic visit + prescription + follow-up, lab report with flags,
optical eye test (also opens job cards for the optical shop), laundry tags."""
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.industry import job_records
from apps.verticals.saloon.models import ServiceCase

from .test_jobs import _clean_cache, _garage, _new_job  # noqa: F401

pytestmark = pytest.mark.django_db


def _job(company, owner, staff, **extra):
    _new_job(owner, staff, **extra)
    return ServiceCase.objects.filter(company=company).latest("id")


def test_clinic_visit_prescription_and_follow_up():
    company, owner, staff = _garage("r1@t.qa", kind="dental_clinic")
    job = _job(company, owner, staff, subject_name="Sara", identifier="MRN-77", title="Tooth pain")
    act = reverse("webapp:job_action", args=[job.id])
    nv = (timezone.localdate() + timedelta(days=7)).isoformat()
    owner.post(act, {"do": "record", "v_bp": "120/80", "v_pulse": "72", "complaint": "Pain lower left",
                     "diagnosis": "Caries 36", "advice": "Soft food",
                     "rx_medicine": ["Amoxicillin 500 mg", "", "Ibuprofen 400 mg"], "rx_dose": ["1 cap", "", "1 tab"],
                     "rx_freq": ["1-1-1", "", "1-0-1"], "rx_days": ["5", "", "3"], "rx_note": ["after food", "", ""],
                     "next_visit": nv})
    job.refresh_from_db()
    assert job.record["vitals"]["bp"] == "120/80" and len(job.record["rx"]) == 2 and job.record["next_visit"] == nv
    page = owner.get(reverse("webapp:service_case_detail", args=[job.id])).content.decode()
    assert "Visit record" in page and "Amoxicillin" in page and "Book the next visit" in page
    rx = owner.get(reverse("webapp:job_print", args=[job.id]) + "?doc=rx").content.decode()
    assert "Prescription" in rx and "Ibuprofen 400 mg" in rx and "MRN-77" in rx and "120/80" in rx
    assert owner.get(reverse("webapp:job_print", args=[job.id]) + "?doc=lab").content.decode().find("Test report") == -1
    r = owner.post(act, {"do": "follow_up", "date": nv})
    follow = ServiceCase.objects.filter(company=company).latest("id")
    assert follow.pk != job.pk and follow.title.startswith("Follow-up") and follow.profile == job.profile
    assert timezone.localtime(follow.scheduled_at).date().isoformat() == nv and r.url.endswith(f"/{follow.id}/")


def test_lab_report_flags():
    company, owner, staff = _garage("r2@t.qa", kind="diagnostic_laboratory")
    job = _job(company, owner, staff, subject_name="Ravi", title="CBC")
    owner.post(reverse("webapp:job_action", args=[job.id]), {
        "do": "record", "sample": "Blood", "res_test": ["Haemoglobin", "WBC", "Sugar (F)"],
        "res_value": ["10.2", "7.5", "130"], "res_unit": ["g/dL", "10^3/uL", "mg/dL"],
        "res_range": ["12-16", "4-11", "<100"]})
    job.refresh_from_db()
    assert [r["flag"] for r in job.record["results"]] == ["L", "", "H"]
    report = owner.get(reverse("webapp:job_print", args=[job.id]) + "?doc=lab").content.decode()
    assert "Test report" in report and "Haemoglobin" in report and "Blood" in report
    assert job_records._flag("abc", "1-2") == "" and job_records._flag("5", ">3") == ""


def test_optical_eye_test_and_laundry_tags():
    company, owner, staff = _garage("r3@t.qa", kind="optical_shop")  # a shop: job cards open through "eye_test"
    assert owner.get(reverse("webapp:service_case_list")).status_code == 200
    job = _job(company, owner, staff, subject_name="Khalid", title="Eye test + glasses")
    owner.post(reverse("webapp:job_action", args=[job.id]), {
        "do": "record", "R_sph": "-1.25", "R_cyl": "-0.50", "R_axis": "180", "L_sph": "-1.00", "pd": "62",
        "frame": "Ray-Ban RB5154", "lens": "Blue-cut 1.56"})
    job.refresh_from_db()
    assert job.record["eye"]["R"]["sph"] == "-1.25" and job.profile.details["eye_rx"]["pd"] == "62"
    second = _job(company, owner, staff, subject_name="Khalid", title="New glasses")
    assert job_records.previous_eye(second) == job
    assert "Last test" in owner.get(reverse("webapp:service_case_detail", args=[second.id])).content.decode()
    eye = owner.get(reverse("webapp:job_print", args=[job.id]) + "?doc=eye").content.decode()
    assert "Eye prescription" in eye and "-1.25" in eye and "Blue-cut" in eye

    company2, owner2, staff2 = _garage("r4@t.qa", kind="laundry_dry_cleaning")
    lj = _job(company2, owner2, staff2, subject_name="", title="Wash & iron")
    act = reverse("webapp:job_action", args=[lj.id])
    owner2.post(act, {"do": "line", "description": "Shirt – wash & iron", "quantity": "3", "unit_price": "5"})
    owner2.post(act, {"do": "line", "description": "Thobe – dry clean", "quantity": "1", "unit_price": "12"})
    tags = job_records.laundry_tags(lj)
    assert [t["tag"] for t in tags] == [f"{lj.number}-{i}" for i in range(1, 5)] and tags[3]["item"] == "Thobe – dry clean"
    sheet = owner2.get(reverse("webapp:job_print", args=[lj.id]) + "?doc=tags").content.decode()
    assert f"{lj.number}-4" in sheet
    # a repair service has no special record (a garage has the vehicle check-in, tested below)
    company3, owner3, staff3 = _garage("r5@t.qa", kind="repair_services")
    assert job_records.kind_for(company3) is None
    gj = _job(company3, owner3, staff3)
    owner3.post(reverse("webapp:job_action", args=[gj.id]), {"do": "record", "v_bp": "1"})
    gj.refresh_from_db()
    assert gj.record == {}


def test_garage_vehicle_check_in_print_and_status_page():
    company, owner, staff = _garage("r9@t.qa", kind="auto_garage")
    job = _job(company, owner, staff, subject_name="Swift VXi", identifier="KL-57-A-1234", title="Full service")
    page = owner.get(reverse("webapp:service_case_detail", args=[job.id])).content.decode()
    assert "Vehicle check-in" in page and "KM reading" in page and "Engine oil" in page
    nd = (timezone.localdate() + timedelta(days=120)).isoformat()
    owner.post(reverse("webapp:job_action", args=[job.id]), {
        "do": "record", "km_in": "45,200", "fuel": "1/2", "chk_engine_oil": "replaced", "chk_brakes": "attention",
        "chk_tyres": "ok", "chk_ac": "bogus", "damage": "Scratch on the rear bumper", "belongings": "Spare wheel, jack",
        "next_km": "50200", "next_date": nd})
    job.refresh_from_db()
    rec = job.record
    assert rec["km_in"] == "45200" and rec["fuel"] == "1/2" and rec["next_km"] == "50200" and rec["next_date"] == nd
    assert rec["checks"]["engine_oil"] == "replaced" and rec["checks"]["brakes"] == "attention" and rec["checks"]["ac"] == ""
    assert job.profile.details["vehicle"]["km"] == "45200" and job.profile.details["vehicle"]["next_km"] == "50200"
    card = owner.get(reverse("webapp:job_print", args=[job.id])).content.decode()
    assert "45200" in card and "Needs attention" in card and "Scratch on the rear bumper" in card and "50200 km" in card
    status = Client().get(reverse("webapp:job_status_page", args=[job.token])).content.decode()
    assert "Next service" in status and "50200 km" in status
    # the next visit of the same car shows the last reading
    nxt = _job(company, owner, staff, subject_name="Swift VXi", identifier="KL-57-A-1234", title="Brake check")
    page = owner.get(reverse("webapp:service_case_detail", args=[nxt.id])).content.decode()
    assert "Last visit" in page and "45200 km" in page


def test_garage_new_job_examples_are_a_car_and_a_plate():
    company, owner, staff = _garage("r10@t.qa", kind="auto_garage")
    page = owner.get(reverse("webapp:service_case_add")).content.decode()
    assert "Maruti Swift VXi" in page and "KL-57-A-1234" in page and "MRN-10023" not in page


def test_computer_shop_service_desk_device_check_in_and_amc():
    company, owner, staff = _garage("r11@t.qa", kind="computer_shop")
    home = owner.get(reverse("webapp:service_case_list")).content.decode()
    assert "Service & repairs" in home and "Service contracts (AMC)" in home
    assert owner.get(reverse("webapp:contract_list")).status_code == 200
    page = owner.get(reverse("webapp:service_case_add")).content.decode()
    assert "HP LaserJet Pro M126nw" in page
    job = _job(company, owner, staff, subject_name="HP LaserJet 1020", identifier="VNC3K12345", title="Paper jam + refill")
    page = owner.get(reverse("webapp:service_case_detail", args=[job.id])).content.decode()
    assert "Device check-in" in page and "Cartridge / toner" in page
    owner.post(reverse("webapp:job_action", args=[job.id]), {
        "do": "record", "item_cartridge": "1", "item_power_cable": "1", "item_bogus": "1", "condition": "Top cover cracked",
        "counter": "18,450", "warranty": "out", "data_ok": "1"})
    job.refresh_from_db()
    rec = job.record
    assert rec["items"] == ["power_cable", "cartridge"] and rec["counter"] == "18450" and rec["warranty"] == "out"
    assert rec["data_ok"] is True
    card = owner.get(reverse("webapp:job_print", args=[job.id])).content.decode()
    assert "Power cable, Cartridge / toner" in card and "Top cover cracked" in card and "Out of warranty" in card
    # a plain shop still has no job cards
    company2, owner2, staff2 = _garage("r12@t.qa", kind="clothing_store")
    assert owner2.get(reverse("webapp:service_case_list")).status_code == 302
    assert owner2.get(reverse("webapp:contract_list")).status_code == 302


def test_bakery_cake_order_with_advance_then_bill_the_balance():
    from decimal import Decimal
    from apps.industry import jobs
    from apps.sales.models import CustomerPayment
    company, owner, staff = _garage("r13@t.qa", kind="bakery")
    board = owner.get(reverse("webapp:service_case_list")).content.decode()
    assert "Cake orders" in board and "New cake order" in board
    page = owner.get(reverse("webapp:service_case_add")).content.decode()
    assert "Cake for (name / occasion)" in page and "Pickup / delivery time" in page and "Ammu&#x27;s 5th birthday" in page
    assert "Chocolate truffle cake 1.5 kg" in page and "Oil change" not in page
    job = _job(company, owner, staff, subject_name="Ammu's birthday", title="Chocolate truffle cake 1.5 kg")
    page = owner.get(reverse("webapp:service_case_detail", args=[job.id])).content.decode()
    assert "Cake details" in page and "Message on the cake" in page
    act = reverse("webapp:job_action", args=[job.id])
    owner.post(act, {"do": "record", "flavour": "Chocolate truffle", "weight_kg": "1.5 kg", "shape": "heart",
                     "eggless": "1", "message": "Happy Birthday Ammu", "advance": "500", "advance_method": "bank"})
    job.refresh_from_db()
    rec = job.record
    assert rec["weight_kg"] == "1.5" and rec["shape"] == "heart" and rec["eggless"] and rec["advance"] == "500.00"
    advance = CustomerPayment.objects.get(id=rec["advance_payment_id"])
    assert advance.invoice is None and advance.method == "bank" and advance.amount == Decimal("500")
    # saving again does not take the advance twice
    owner.post(act, {"do": "record", "flavour": "Chocolate truffle", "weight_kg": "1.5", "shape": "heart", "eggless": "1",
                     "message": "Happy Birthday Ammu", "advance": "500"})
    assert CustomerPayment.objects.filter(company=company).count() == 1
    owner.post(act, {"do": "line", "description": "Chocolate truffle cake 1.5 kg", "quantity": "1", "unit_price": "1350"})
    slip = owner.get(reverse("webapp:job_print", args=[job.id])).content.decode()
    assert "Happy Birthday Ammu" in slip and "Eggless" in slip and "850.00" in slip
    jobs.set_status(job, "in_progress"); jobs.set_status(job, "ready")
    invoice = jobs.bill(job, staff.company.memberships.first().user, method="cash")
    advance.refresh_from_db()
    assert advance.invoice == invoice and invoice.status == "paid" and invoice.amount_paid == Decimal("1350")
    assert CustomerPayment.objects.get(invoice=invoice, method="cash").amount == Decimal("850")


def test_clinic_words_and_previous_visits():
    company, owner, staff = _garage("r14@t.qa", kind="medical_clinic")
    board = owner.get(reverse("webapp:service_case_list")).content.decode()
    assert "OP / patient visits" in board and "New OP visit" in board and "Consultation done" in board
    first = _job(company, owner, staff, subject_name="Leela", identifier="OP-1008", title="Knee pain")
    owner.post(reverse("webapp:job_action", args=[first.id]), {
        "do": "record", "v_bp": "140/90", "complaint": "Knee pain", "diagnosis": "Osteoarthritis knee",
        "rx_medicine": ["Aceclofenac 100 mg"], "rx_dose": ["1 tab"], "rx_freq": ["1-0-1"], "rx_days": ["5"], "rx_note": [""]})
    second = _job(company, owner, staff, subject_name="Leela", identifier="OP-1008", title="Review")
    page = owner.get(reverse("webapp:service_case_detail", args=[second.id])).content.decode()
    assert "Previous visits (1)" in page and "Osteoarthritis knee" in page and "Aceclofenac 100 mg 1-0-1" in page
    assert "Call in" in page and "Waiting (lab / tests)" in page
