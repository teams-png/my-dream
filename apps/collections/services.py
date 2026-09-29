"""
Phase 30 — Accounts Receivable and Payable Maturity Management.

Everything here is computed straight from posted documents/payments
(SalesInvoice/Purchase total, amount_paid, status) — never from a cached
customer/supplier "balance" field (Phase 30 rule: "do not calculate
outstanding from customer master balances").
"""
from decimal import Decimal
from datetime import date as _date

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import AgeingBucket, DEFAULT_AGEING_BUCKETS, CollectionNote, OverdueNotification


# ---------------------------------------------------------------- buckets


def seed_default_ageing_buckets(company):
    """Idempotent — called once at company creation, alongside chart-of-
    accounts/role seeding, and by a data migration for existing companies."""
    for label, min_days, max_days, order in DEFAULT_AGEING_BUCKETS:
        AgeingBucket.objects.get_or_create(
            company=company, label=label,
            defaults={"min_days": min_days, "max_days": max_days, "order": order},
        )


def get_ageing_buckets(company):
    return list(AgeingBucket.objects.for_company(company).order_by("order"))


def _bucket_for_days(buckets, days_overdue):
    for bucket in buckets:
        if bucket.matches(days_overdue):
            return bucket
    return None  # config gap — caller falls back to an "unbucketed" total


# ---------------------------------------------------------------- shared ageing engine


def _ageing(*, company, queryset, party_field, as_of=None):
    """
    Shared engine for both AR and AP: `queryset` is SalesInvoice or
    Purchase rows already filtered to non-paid/non-void for this company;
    `party_field` is "customer" or "supplier". Returns (detail_rows, buckets_used).
    """
    as_of = as_of or timezone.localdate()
    if isinstance(as_of, str):
        from django.utils.dateparse import parse_date
        as_of = parse_date(as_of)

    buckets = get_ageing_buckets(company)
    rows = []
    for doc in queryset:
        outstanding = doc.total - doc.amount_paid
        if outstanding <= 0:
            continue  # fully paid in substance even if status hasn't caught up

        if doc.due_date is None:
            row_bucket = "no_due_date"
            days_overdue = None
        elif doc.due_date > as_of:
            row_bucket = "not_due"
            days_overdue = 0
        else:
            days_overdue = (as_of - doc.due_date).days
            matched = _bucket_for_days(buckets, days_overdue)
            row_bucket = matched.label if matched else "unbucketed_overdue"

        rows.append({
            "document": doc,
            "party": getattr(doc, party_field),
            "due_date": doc.due_date,
            "days_overdue": days_overdue,
            "outstanding": outstanding,
            "bucket": row_bucket,
        })
    return rows, buckets


def _summarize(rows, buckets):
    summary = {
        "not_due": Decimal("0"),
        "no_due_date": Decimal("0"),
        "unbucketed_overdue": Decimal("0"),
        "buckets": [
            {"label": b.label, "min_days": b.min_days, "max_days": b.max_days, "total": Decimal("0"), "count": 0}
            for b in buckets
        ],
    }
    bucket_index = {b["label"]: b for b in summary["buckets"]}
    total_outstanding = Decimal("0")

    for row in rows:
        total_outstanding += row["outstanding"]
        label = row["bucket"]
        if label in ("not_due", "no_due_date", "unbucketed_overdue"):
            summary[label] += row["outstanding"]
        else:
            bucket_index[label]["total"] += row["outstanding"]
            bucket_index[label]["count"] += 1

    summary["total_outstanding"] = total_outstanding
    return summary


# ---------------------------------------------------------------- AR (customers)


def ar_ageing_detail(company, as_of=None):
    from apps.sales.models import SalesInvoice
    qs = SalesInvoice.objects.for_company(company).exclude(status__in=["paid", "void"]).select_related("customer")
    rows, _ = _ageing(company=company, queryset=qs, party_field="customer", as_of=as_of)
    return rows


def ar_ageing_summary(company, as_of=None):
    from apps.sales.models import SalesInvoice
    qs = SalesInvoice.objects.for_company(company).exclude(status__in=["paid", "void"]).select_related("customer")
    rows, buckets = _ageing(company=company, queryset=qs, party_field="customer", as_of=as_of)
    return _summarize(rows, buckets)


# ---------------------------------------------------------------- AP (suppliers)


def ap_ageing_detail(company, as_of=None):
    from apps.purchases.models import Purchase
    qs = Purchase.objects.for_company(company).exclude(status="paid").select_related("supplier")
    rows, _ = _ageing(company=company, queryset=qs, party_field="supplier", as_of=as_of)
    return rows


def ap_ageing_summary(company, as_of=None):
    from apps.purchases.models import Purchase
    qs = Purchase.objects.for_company(company).exclude(status="paid").select_related("supplier")
    rows, buckets = _ageing(company=company, queryset=qs, party_field="supplier", as_of=as_of)
    return _summarize(rows, buckets)


# ---------------------------------------------------------------- credit limit


def customer_credit_status(company, customer):
    """
    Outstanding reconciled from posted invoices (same rule as ageing
    above), never from a cached balance. `credit_limit=0` means no limit
    is enforced — `over_limit` is always False in that case.
    """
    if customer.company_id != company.id:
        raise ValidationError("This customer does not belong to the active company.")

    from apps.sales.models import SalesInvoice
    outstanding = SalesInvoice.objects.for_company(company).filter(customer=customer).exclude(
        status__in=["paid", "void"]
    )
    total_outstanding = sum((inv.total - inv.amount_paid for inv in outstanding), Decimal("0"))
    total_outstanding = max(total_outstanding, Decimal("0"))

    over_limit = bool(customer.credit_limit) and total_outstanding > customer.credit_limit
    available = (customer.credit_limit - total_outstanding) if customer.credit_limit else None

    return {
        "customer": customer,
        "credit_limit": customer.credit_limit,
        "outstanding": total_outstanding,
        "available_credit": available,
        "over_limit": over_limit,
    }


# ---------------------------------------------------------------- collection notes


def record_collection_note(*, company, user, party_type, note, customer=None, supplier=None, invoice=None, purchase=None, follow_up_date=None):
    if party_type not in ("customer", "supplier"):
        raise ValidationError("party_type must be 'customer' or 'supplier'.")
    if party_type == "customer" and not customer:
        raise ValidationError("customer is required when party_type='customer'.")
    if party_type == "supplier" and not supplier:
        raise ValidationError("supplier is required when party_type='supplier'.")
    if customer and customer.company_id != company.id:
        raise ValidationError("This customer does not belong to the active company.")
    if supplier and supplier.company_id != company.id:
        raise ValidationError("This supplier does not belong to the active company.")
    if invoice and invoice.company_id != company.id:
        raise ValidationError("This invoice does not belong to the active company.")
    if purchase and purchase.company_id != company.id:
        raise ValidationError("This purchase does not belong to the active company.")

    return CollectionNote.objects.create(
        company=company, party_type=party_type, customer=customer, supplier=supplier,
        invoice=invoice, purchase=purchase, note=note, follow_up_date=follow_up_date, created_by=user,
    )


# ---------------------------------------------------------------- overdue notifications (dedup by bucket)


def generate_overdue_notifications(company, as_of=None):
    """
    Notifies once per (document, bucket) — replaces the old "already
    notified today" dedup (apps.notifications.services), which re-sent a
    notification every single day a document stayed overdue. Called by
    apps.notifications.services.check_overdue_invoices_and_notify /
    check_overdue_bills_and_notify, so the existing Celery beat task and
    webapp call sites get this behaviour with no changes on their end.
    """
    from apps.notifications.services import notify_invoice_overdue, notify_bill_overdue

    created = []
    for row in ar_ageing_detail(company, as_of=as_of):
        if row["bucket"] in ("not_due", "no_due_date"):
            continue
        marker, is_new = OverdueNotification.objects.get_or_create(
            company=company, source_type="sales_invoice", source_id=row["document"].id, bucket_label=row["bucket"],
        )
        if is_new:
            created.append(notify_invoice_overdue(company, row["document"]))

    for row in ap_ageing_detail(company, as_of=as_of):
        if row["bucket"] in ("not_due", "no_due_date"):
            continue
        marker, is_new = OverdueNotification.objects.get_or_create(
            company=company, source_type="purchase", source_id=row["document"].id, bucket_label=row["bucket"],
        )
        if is_new:
            created.append(notify_bill_overdue(company, row["document"]))

    return created
