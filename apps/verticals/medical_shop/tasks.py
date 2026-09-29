from celery import shared_task

from apps.tenants.models import Company

from .services import check_expiring_batches


@shared_task
def check_medicine_batch_expiry():
    """Wires medical_shop.services.check_expiring_batches into the daily beat schedule (see config/celery.py)."""
    companies = Company.objects.filter(
        is_active=True,
        company_modules__module__code="medical_shop",
        company_modules__is_active=True,
    ).distinct()
    for company in companies:
        check_expiring_batches(company)
