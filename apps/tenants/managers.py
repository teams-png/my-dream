from django.db import models


class TenantQuerySet(models.QuerySet):
    def for_company(self, company):
        return self.filter(company=company)


class TenantManager(models.Manager):
    """
    Deliberately does NOT provide an easy 'give me everything across all
    tenants' shortcut. Service-layer code should always write
    `Model.objects.for_company(request.company)` (or `.filter(company=...)`),
    never a bare `Model.objects.all()` on a tenant-scoped model.

    A lint rule / code-review checklist (Phase 0 Section 3) backs this up;
    this manager is the runtime half of that enforcement.
    """
    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_company(self, company):
        return self.get_queryset().for_company(company)
