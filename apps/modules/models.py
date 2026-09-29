from django.db import models


class BusinessType(models.Model):
    code = models.SlugField(unique=True)   # "gym", "textile", "general_retail", ...
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Module(models.Model):
    code = models.SlugField(unique=True)   # "accounting", "gym", ...
    name = models.CharField(max_length=100)
    is_core = models.BooleanField(default=False)  # core modules always active, never toggled off

    def __str__(self):
        return self.name


class BusinessTypeDefaultModule(models.Model):
    business_type = models.ForeignKey(BusinessType, on_delete=models.CASCADE, related_name="default_modules")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("business_type", "module")


class CompanyModule(models.Model):
    company = models.ForeignKey("tenants.Company", on_delete=models.CASCADE, related_name="company_modules")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    activated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("company", "module")
