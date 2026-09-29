"""
Phase 30 — Accounts Receivable and Payable Maturity Management.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


def _make_invoice(company, user, customer, fixtures, total_qty=1, unit_price=Decimal("100.00"), due_date=None, date="2026-01-01"):
    from apps.sales.services import create_invoice
    return create_invoice(
        company=company, user=user, customer=customer, date=date,
        lines=[{"product": fixtures["product"], "quantity": total_qty, "unit_price": unit_price}],
        warehouse=fixtures["warehouse"], due_date=due_date,
    )


def _make_purchase(company, user, supplier, fixtures, total_qty=1, unit_cost=Decimal("100.00"), due_date=None, date="2026-01-01"):
    from apps.purchases.services import create_purchase
    return create_purchase(
        company=company, user=user, supplier=supplier, date=date,
        lines=[{"product": fixtures["product"], "quantity": total_qty, "unit_cost": unit_cost}],
        warehouse=fixtures["warehouse"], due_date=due_date,
    )


@pytest.fixture
def supplier_a(tenant_a):
    from apps.suppliers.models import Supplier
    return Supplier.objects.create(company=tenant_a, name="Acme Supplies")


class TestDueDateDefaults:
    def test_invoice_due_date_defaults_from_customer_payment_terms(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        fixtures = sales_fixtures_factory(tenant_a)
        fixtures["customer"].payment_terms_days = 15
        fixtures["customer"].save(update_fields=["payment_terms_days"])

        invoice = _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, date="2026-01-01")
        assert str(invoice.due_date) == "2026-01-16"

    def test_purchase_due_date_defaults_from_supplier_payment_terms(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        fixtures = sales_fixtures_factory(tenant_a)
        supplier_a.payment_terms_days = 45
        supplier_a.save(update_fields=["payment_terms_days"])

        purchase = _make_purchase(tenant_a, tenant_a_owner, supplier_a, fixtures, date="2026-01-01")
        assert str(purchase.due_date) == "2026-02-15"


class TestARAgeing:
    def test_future_due_invoice_is_not_shown_as_overdue(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.collections.services import ar_ageing_summary, ar_ageing_detail

        fixtures = sales_fixtures_factory(tenant_a)
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, due_date="2026-06-01", date="2026-01-01")

        summary = ar_ageing_summary(tenant_a, as_of="2026-02-01")
        assert summary["not_due"] == Decimal("100.00")
        assert all(b["total"] == Decimal("0") for b in summary["buckets"])

        detail = ar_ageing_detail(tenant_a, as_of="2026-02-01")
        assert detail[0]["bucket"] == "not_due"
        assert detail[0]["days_overdue"] == 0

    def test_overdue_invoice_lands_in_correct_bucket(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.collections.services import ar_ageing_summary

        fixtures = sales_fixtures_factory(tenant_a)
        # Due 2026-01-01, as_of 2026-02-15 -> 45 days overdue -> "31-60" bucket
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, due_date="2026-01-01", date="2025-12-01")

        summary = ar_ageing_summary(tenant_a, as_of="2026-02-15")
        bucket = {b["label"]: b for b in summary["buckets"]}["31-60"]
        assert bucket["total"] == Decimal("100.00")
        assert bucket["count"] == 1
        assert summary["not_due"] == Decimal("0")

    def test_partial_payment_moves_only_remaining_balance_into_ageing(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import record_customer_payment
        from apps.collections.services import ar_ageing_summary

        fixtures = sales_fixtures_factory(tenant_a)
        invoice = _make_invoice(
            tenant_a, tenant_a_owner, fixtures["customer"], fixtures,
            total_qty=1, unit_price=Decimal("500.00"), due_date="2025-01-01", date="2024-12-01",
        )
        record_customer_payment(
            company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"],
            amount=Decimal("300.00"), date="2025-01-05", invoice=invoice,
        )

        summary = ar_ageing_summary(tenant_a, as_of="2025-06-01")
        assert summary["total_outstanding"] == Decimal("200.00")

    def test_fully_paid_invoice_excluded_from_ageing(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.sales.services import record_customer_payment
        from apps.collections.services import ar_ageing_summary

        fixtures = sales_fixtures_factory(tenant_a)
        invoice = _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures,
                                 unit_price=Decimal("100.00"), due_date="2025-01-01", date="2024-12-01")
        record_customer_payment(company=tenant_a, user=tenant_a_owner, customer=fixtures["customer"],
                                 amount=Decimal("100.00"), date="2025-01-02", invoice=invoice)

        summary = ar_ageing_summary(tenant_a, as_of="2025-06-01")
        assert summary["total_outstanding"] == Decimal("0")

    def test_ageing_totals_reconcile_with_raw_outstanding(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.collections.services import ar_ageing_summary
        from apps.sales.models import SalesInvoice

        fixtures = sales_fixtures_factory(tenant_a)
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, unit_price=Decimal("100.00"), due_date="2026-06-01", date="2026-01-01")
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, unit_price=Decimal("250.00"), due_date="2025-01-01", date="2024-12-01")

        summary = ar_ageing_summary(tenant_a, as_of="2026-03-01")
        raw_total = sum(
            (inv.total - inv.amount_paid)
            for inv in SalesInvoice.objects.for_company(tenant_a).exclude(status__in=["paid", "void"])
        )
        assert summary["total_outstanding"] == raw_total


class TestAPAgeing:
    def test_ap_ageing_mirrors_ar_behaviour(self, tenant_a, tenant_a_owner, sales_fixtures_factory, supplier_a):
        from apps.collections.services import ap_ageing_summary

        fixtures = sales_fixtures_factory(tenant_a)
        _make_purchase(tenant_a, tenant_a_owner, supplier_a, fixtures, unit_cost=Decimal("400.00"), due_date="2026-01-01", date="2025-12-01")

        summary = ap_ageing_summary(tenant_a, as_of="2026-01-20")
        bucket = {b["label"]: b for b in summary["buckets"]}["0-30"]
        assert bucket["total"] == Decimal("400.00")


class TestCreditLimit:
    def test_over_limit_flagged(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.collections.services import customer_credit_status

        fixtures = sales_fixtures_factory(tenant_a)
        fixtures["customer"].credit_limit = Decimal("50.00")
        fixtures["customer"].save(update_fields=["credit_limit"])
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, unit_price=Decimal("100.00"))

        status = customer_credit_status(tenant_a, fixtures["customer"])
        assert status["over_limit"] is True
        assert status["outstanding"] == Decimal("100.00")

    def test_zero_limit_means_unlimited(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.collections.services import customer_credit_status

        fixtures = sales_fixtures_factory(tenant_a)
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, unit_price=Decimal("100000.00"))

        status = customer_credit_status(tenant_a, fixtures["customer"])
        assert status["over_limit"] is False
        assert status["available_credit"] is None

    def test_credit_status_rejects_cross_tenant_customer(self, tenant_a, tenant_b, sales_fixtures_factory):
        from apps.collections.services import customer_credit_status

        fixtures_b = sales_fixtures_factory(tenant_b)
        with pytest.raises(ValidationError, match="active company"):
            customer_credit_status(tenant_a, fixtures_b["customer"])


class TestCollectionNotes:
    def test_record_note_against_customer(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.collections.services import record_collection_note
        from apps.collections.models import CollectionNote

        fixtures = sales_fixtures_factory(tenant_a)
        note = record_collection_note(
            company=tenant_a, user=tenant_a_owner, party_type="customer",
            customer=fixtures["customer"], note="Called, promised payment Friday.",
            follow_up_date="2026-02-10",
        )
        assert CollectionNote.objects.filter(id=note.id, customer=fixtures["customer"]).exists()

    def test_note_requires_matching_party_field(self, tenant_a, sales_fixtures_factory, tenant_a_owner):
        from apps.collections.services import record_collection_note

        fixtures = sales_fixtures_factory(tenant_a)
        with pytest.raises(ValidationError, match="customer is required"):
            record_collection_note(company=tenant_a, user=tenant_a_owner, party_type="customer", note="x")


class TestOverdueNotificationDedup:
    def test_same_bucket_does_not_renotify(self, tenant_a, tenant_a_owner, sales_fixtures_factory):
        from apps.notifications.services import check_overdue_invoices_and_notify
        from apps.notifications.models import Notification

        fixtures = sales_fixtures_factory(tenant_a)
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, unit_price=Decimal("100.00"), due_date="2026-01-01", date="2025-12-01")

        first = check_overdue_invoices_and_notify(tenant_a)
        assert len(first) == 1

        # Running again the "next day" but still in the same 0-30 bucket -> no new notification.
        second = check_overdue_invoices_and_notify(tenant_a)
        assert len(second) == 0
        assert Notification.objects.filter(company=tenant_a, notif_type="invoice_overdue").count() == 1

    def test_escalating_to_next_bucket_notifies_again(self, tenant_a, tenant_a_owner, sales_fixtures_factory, monkeypatch):
        from apps.collections import services as collections_services
        from apps.notifications.services import check_overdue_invoices_and_notify

        fixtures = sales_fixtures_factory(tenant_a)
        _make_invoice(tenant_a, tenant_a_owner, fixtures["customer"], fixtures, unit_price=Decimal("100.00"), due_date="2026-01-01", date="2025-12-01")

        # Day 10 overdue -> bucket "0-30"
        check_overdue_invoices_and_notify(tenant_a)

        # Simulate 45 days overdue -> bucket "31-60" by monkeypatching timezone.localdate used as default as_of.
        import apps.collections.services as svc

        real_ageing = svc._ageing

        def _ageing_with_fixed_as_of(*args, **kwargs):
            kwargs["as_of"] = "2026-02-15"
            return real_ageing(*args, **kwargs)

        monkeypatch.setattr(svc, "_ageing", _ageing_with_fixed_as_of)

        second = check_overdue_invoices_and_notify(tenant_a)
        assert len(second) == 1


class TestAgeingBucketApi:
    def test_owner_can_view_ar_ageing(self, tenant_a, as_tenant_a_owner):
        resp = as_tenant_a_owner.get("/api/collections/ar-ageing/summary/")
        assert resp.status_code == 200, resp.data
        assert "buckets" in resp.data

    def test_default_buckets_seeded_on_signup(self, tenant_a, as_tenant_a_owner):
        resp = as_tenant_a_owner.get("/api/collections/ageing-buckets/")
        assert resp.status_code == 200
        labels = {b["label"] for b in resp.data}
        assert labels == {"0-30", "31-60", "61-90", "90+"}

    def test_staff_can_view_but_not_manage_notes(self, tenant_a, member_factory):
        from conftest import jwt_client

        staff = member_factory(tenant_a, "Staff")
        client = jwt_client(staff)

        resp = client.get("/api/collections/ar-ageing/summary/")
        assert resp.status_code == 200

        resp = client.post("/api/collections/notes/", {"party_type": "customer", "note": "x"})
        assert resp.status_code == 403
