from django.contrib import admin
from .models import Vehicle, WashPackage, WashOrder

admin.site.register(Vehicle)
admin.site.register(WashPackage)
admin.site.register(WashOrder)
