from django.contrib import admin
from .models import Quotation, SalesOrder, SalesInvoice, SalesInvoiceLine, CustomerPayment, SalesReturn


class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 0


@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "company", "customer", "date", "total", "status")
    list_filter = ("status",)
    inlines = [SalesInvoiceLineInline]


admin.site.register(Quotation)
admin.site.register(SalesOrder)
admin.site.register(CustomerPayment)
admin.site.register(SalesReturn)
