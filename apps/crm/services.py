from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone

from apps.customers.models import Customer
from apps.sales.models import Quotation
from .models import Lead, Opportunity, PipelineStage


def duplicate_customer_candidates(*, company, lead):
    query = Q()
    if lead.email:
        query |= Q(email__iexact=lead.email)
    if lead.phone:
        query |= Q(phone=lead.phone)
    if lead.name:
        query |= Q(name__iexact=lead.name)
    if not query:
        return Customer.objects.none()
    return Customer.objects.for_company(company).filter(query)


@transaction.atomic
def convert_lead(*, company, lead, user, existing_customer=None, resolve_duplicate=False, create_quotation=False):
    lead = Lead.objects.select_for_update().get(company=company, pk=lead.pk)
    if lead.status == "converted":
        raise ValidationError("Lead has already been converted.")
    candidates = duplicate_customer_candidates(company=company, lead=lead)
    if existing_customer is not None:
        if existing_customer.company_id != company.id:
            raise ValidationError("Customer belongs to another company.")
        customer = existing_customer
    elif candidates.exists() and not resolve_duplicate:
        raise ValidationError({"duplicate_candidates": list(candidates.values("id", "name", "email", "phone"))})
    else:
        customer = candidates.first() if candidates.exists() else Customer.objects.create(
            company=company, name=lead.name, email=lead.email, phone=lead.phone,
        )
    lead.status = "converted"
    lead.converted_customer = customer
    lead.save(update_fields=("status", "converted_customer", "updated_at"))
    stage, _ = PipelineStage.objects.get_or_create(
        company=company, name="Qualified", defaults={"order": 20, "probability": 50},
    )
    opportunity = Opportunity.objects.create(
        company=company, lead=lead, customer=customer, title=f"{customer.name} opportunity",
        stage=stage, assigned_to=lead.assigned_to or user,
    )
    quotation = None
    if create_quotation:
        quotation = Quotation.objects.create(
            company=company, customer=customer, date=timezone.localdate(), created_by=user,
            notes=f"Created from CRM lead #{lead.id}",
        )
    return customer, opportunity, quotation


def pipeline_summary(*, company, user=None, manager=False):
    qs = Opportunity.objects.for_company(company).select_related("stage")
    if user is not None and not manager:
        qs = qs.filter(assigned_to=user)
    return list(qs.values("stage_id", "stage__name", "stage__order").annotate(count=Count("id"), total=Sum("expected_value")).order_by("stage__order"))


def customer_timeline(*, company, customer):
    if customer.company_id != company.id:
        raise ValidationError("Customer belongs to another company.")
    events = []
    for row in Opportunity.objects.for_company(company).filter(customer=customer).select_related("stage"):
        events.append({"type": "opportunity", "id": row.id, "date": row.created_at, "title": row.title, "status": row.stage.name})
    for row in Quotation.objects.for_company(company).filter(customer=customer):
        events.append({"type": "quotation", "id": row.id, "date": row.created_at, "title": f"Quotation #{row.id}", "status": row.status})
    for row in customer.salesinvoice_set.select_related().all():
        events.append({"type": "invoice", "id": row.id, "date": row.date, "title": row.invoice_number, "status": row.status, "amount": str(row.total)})
    for row in customer.customerpayment_set.all():
        events.append({"type": "payment", "id": row.id, "date": row.date, "title": "Customer payment", "amount": str(row.amount)})
    return sorted(events, key=lambda e: str(e["date"]), reverse=True)
