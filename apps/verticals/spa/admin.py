from django.contrib import admin
from .models import SpaService, ServicePackage, CustomerPackage, Appointment

admin.site.register(SpaService)
admin.site.register(ServicePackage)
admin.site.register(CustomerPackage)
admin.site.register(Appointment)
