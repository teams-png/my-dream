from django.contrib import admin
from .models import SaloonService, ServicePackage, CustomerPackage, Appointment

admin.site.register(SaloonService)
admin.site.register(ServicePackage)
admin.site.register(CustomerPackage)
admin.site.register(Appointment)
