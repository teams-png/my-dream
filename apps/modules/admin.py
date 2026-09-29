from django.contrib import admin
from .models import BusinessType, Module, BusinessTypeDefaultModule, CompanyModule

admin.site.register(BusinessType)
admin.site.register(Module)
admin.site.register(BusinessTypeDefaultModule)
admin.site.register(CompanyModule)
