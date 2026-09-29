import pytest
from django.core.management import call_command
from django.template.loader import get_template

from apps.modules.catalog import (BUSINESS_PROFILES, BUSINESS_TYPE_MAP, RETAIL_TYPES, SERVICE_TYPES,
                                  PROJECT_TYPES, RESTAURANT_TYPES, business_group, business_profile)
from apps.modules.models import BusinessType, BusinessTypeDefaultModule
from apps.webapp.forms import RegisterClientForm
from apps.webapp.forms import BusinessProductForm, ServiceClientProfileForm
from apps.inventory.models import Product
from apps.verticals.construction.models import ProjectMilestone, ProjectTask, ProjectTimesheet
from apps.verticals.saloon.models import ServiceClientProfile, ServiceCase, ServiceCaseNote


pytestmark = pytest.mark.django_db


def test_every_registration_type_is_seeded_with_core_and_suite_modules():
    call_command("seed_platform")
    assert set(dict(RegisterClientForm.BUSINESS_TYPES)) == set(BUSINESS_TYPE_MAP)
    for code in BUSINESS_TYPE_MAP:
        business_type = BusinessType.objects.get(code=code)
        modules = set(BusinessTypeDefaultModule.objects.filter(
            business_type=business_type
        ).values_list("module__code", flat=True))
        assert {"accounting", "customers", "suppliers", "inventory", "sales", "purchases", "expenses"} <= modules
        if code in RETAIL_TYPES: assert "retail_suite" in modules
        if code in SERVICE_TYPES: assert "service_suite" in modules
        if code in PROJECT_TYPES: assert "project_suite" in modules
        if code in RESTAURANT_TYPES: assert "restaurant" in modules


def test_boutique_and_general_retail_do_not_fall_back_to_mobile_menu():
    source = get_template("base.html").template.source
    assert '{% elif active_business_group == "retail" %}' in source
    assert '{% elif active_business_group == "service" %}' in source
    assert '{% elif active_business_group == "project" %}' in source
    fallback = source[source.rindex("{% else %}"):]
    assert "Phone Units" not in fallback


def test_expanded_catalogue_contains_every_requested_business_family():
    expected = {
        "restaurant", "cafe_juice_shop", "catering_company", "car_rental", "equipment_rental",
        "property_management", "hotel_apartment", "nursery_daycare", "school_training_institute",
        "logistics_transport", "courier_delivery", "travel_agency", "optical_shop",
        "diagnostic_laboratory", "fuel_station", "footwear_store", "baby_products_store",
        "toys_gift_shop", "home_appliances_store", "electrical_plumbing_store",
        "building_materials_store", "tyre_battery_shop", "fish_meat_shop",
        "fruits_vegetables_shop", "ecommerce_store", "mobile_accessories_shop", "uniform_shop",
        "kitchenware_store", "musical_instruments_store", "agricultural_supplies_store", "law_firm",
        "insurance_brokerage", "pest_control", "moving_packing", "interior_design",
        "ac_maintenance", "electronics_repair", "computer_repair", "home_nursing",
        "cleaning_equipment_service", "document_clearing", "real_estate_brokerage",
        "facility_management", "wedding_party_hall", "coworking_space",
    }
    assert expected <= set(BUSINESS_TYPE_MAP)
    assert len(BUSINESS_TYPE_MAP) == 108
    assert business_group("restaurant") == "restaurant"
    assert business_group("car_rental") == "service"
    assert business_group("property_management") == "project"


def test_every_business_type_has_complete_adaptive_profile():
    assert set(BUSINESS_PROFILES) == set(BUSINESS_TYPE_MAP)
    for code, profile in BUSINESS_PROFILES.items():
        assert profile["code"] == code
        assert profile["name"]
        assert profile["group"] == business_group(code)
        if profile["group"] == "service":
            assert profile["profile_type"] in {"person", "student", "pet", "vehicle", "asset", "organization"}
            assert profile["work_label"] and profile["records_label"]
        if profile["group"] == "project":
            assert profile["projects_label"] and profile["provider_label"] and profile["location_label"]


def test_service_and_project_profiles_use_industry_terms():
    assert business_profile("veterinary_clinic")["profile_type"] == "pet"
    assert business_profile("auto_garage")["profile_type"] == "vehicle"
    assert business_profile("driving_school")["profile_type"] == "student"
    assert business_profile("event_management")["projects_label"] == "Events"
    assert business_profile("logistics_transport")["provider_label"] == "Drivers / Carriers"


def test_previously_generic_retail_types_have_industry_fields():
    expected = {
        "general_retail": {"brand_code", "barcode_type", "shelf_location"},
        "ladies_fashion_boutique": {"size_range", "colour_range", "material_spec", "design_reference"},
        "trading_company": {"supplier_code", "hs_code", "minimum_order_quantity"},
        "wholesale_business": {"supplier_code", "minimum_order_quantity", "carton_reference"},
        "import_export": {"hs_code", "country_of_origin", "lead_time_days"},
        "industrial_services": {"technical_specs", "certification", "service_interval_days"},
    }
    for code, fields in expected.items():
        assert fields <= set(BusinessProductForm.INDUSTRY_FIELDS[code])


def test_industry_product_form_persists_bookstore_fields(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="BOOK-FORM-BASE")
    tenant_a.business_type = BusinessType.objects.get_or_create(code="book_store", defaults={"name": "Book Store"})[0]
    tenant_a.save(update_fields=["business_type"])
    form = BusinessProductForm({"sku": "ISBN-1", "name": "Math Book", "unit": f["unit"].id,
        "cost_price": "10", "selling_price": "20", "reorder_level": "2", "isbn": "978123",
        "author": "Author", "publisher": "Publisher", "grade_subject": "Grade 1 Maths"}, company=tenant_a)
    assert form.is_valid(), form.errors
    product = form.save(commit=False); product.company = tenant_a; product.save()
    assert product.attributes["isbn"] == "978123"


def test_expanded_retail_form_persists_restaurant_fields(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="MENU-BASE")
    tenant_a.business_type = BusinessType.objects.get_or_create(
        code="restaurant", defaults={"name": "Restaurant / Cafeteria"},
    )[0]
    tenant_a.save(update_fields=["business_type"])
    form = BusinessProductForm({
        "sku": "MENU-1", "name": "Chicken Meal", "unit": f["unit"].id,
        "cost_price": "10", "selling_price": "20", "reorder_level": "0",
        "item_type": "Main course", "preparation_minutes": "15",
        "ingredients": "Chicken, rice", "allergens": "None",
    }, company=tenant_a)
    assert form.is_valid(), form.errors
    product = form.save(commit=False); product.company = tenant_a; product.save()
    assert product.attributes["item_type"] == "Main course"
    assert product.attributes["preparation_minutes"] == 15


def test_generic_service_profile_case_and_note(tenant_a, tenant_a_owner, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="SERVICE-BASE")
    profile = ServiceClientProfile.objects.create(company=tenant_a, customer=f["customer"], profile_type="vehicle", subject_name="Toyota", identifier="QAT-123")
    case = ServiceCase.objects.create(company=tenant_a, profile=profile, title="Engine diagnosis", opened_date="2026-01-01")
    ServiceCaseNote.objects.create(company=tenant_a, case=case, date="2026-01-02", note_type="Diagnosis", notes="Battery weak", created_by=tenant_a_owner)
    assert case.case_notes.count() == 1


def test_project_milestone_task_and_timesheet(tenant_a, sales_fixtures_factory):
    f = sales_fixtures_factory(tenant_a, sku="PROJECT-BASE")
    from apps.employees.models import Employee
    employee = Employee.objects.create(company=tenant_a, name="Worker")
    from apps.verticals.construction.models import Project
    project = Project.objects.create(company=tenant_a, name="Website", client=f["customer"], start_date="2026-01-01")
    milestone = ProjectMilestone.objects.create(company=tenant_a, project=project, name="Launch", amount=1000)
    task = ProjectTask.objects.create(company=tenant_a, project=project, milestone=milestone, title="Deploy", assigned_to=employee)
    sheet = ProjectTimesheet.objects.create(company=tenant_a, project=project, task=task, employee=employee, date="2026-01-02", hours=2, hourly_rate=50)
    assert sheet.cost == 100
