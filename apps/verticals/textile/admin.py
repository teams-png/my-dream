from django.contrib import admin
from .models import FabricDetail, Measurement, TailoringOrder

admin.site.register(FabricDetail)
admin.site.register(Measurement)
admin.site.register(TailoringOrder)
