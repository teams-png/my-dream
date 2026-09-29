from django.contrib import admin
from .models import (
    MobileUnit, MobileRepairJob, MobileRepairPart, MobileTradeIn,
    MobileWarrantyClaim, MobileInstallmentPlan, MobileInstallmentPayment,
)


@admin.register(MobileUnit)
class MobileUnitAdmin(admin.ModelAdmin):
    list_display = ("imei", "product", "status", "condition", "sold_price", "sold_date")
    list_filter = ("status", "condition")
    search_fields = ("imei", "serial_number")


admin.site.register(MobileRepairJob)
admin.site.register(MobileRepairPart)
admin.site.register(MobileTradeIn)
admin.site.register(MobileWarrantyClaim)
admin.site.register(MobileInstallmentPlan)
admin.site.register(MobileInstallmentPayment)
