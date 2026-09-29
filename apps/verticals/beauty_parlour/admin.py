from django.contrib import admin
from .models import BeautyService, ServicePackage, CustomerPackage, Appointment

admin.site.register(BeautyService)
admin.site.register(ServicePackage)
admin.site.register(CustomerPackage)
admin.site.register(Appointment)
