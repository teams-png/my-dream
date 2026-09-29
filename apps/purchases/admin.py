from django.contrib import admin
from .models import PurchaseOrder, Purchase, PurchaseLine, SupplierPayment, PurchaseReturn


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "supplier", "date", "total", "status")
    list_filter = ("status",)
    inlines = [PurchaseLineInline]


admin.site.register(PurchaseOrder)
admin.site.register(SupplierPayment)
admin.site.register(PurchaseReturn)
