from django.contrib import admin
from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("subject", "company", "status", "priority", "assigned_to", "created_at")
    list_filter = ("status", "priority")
    search_fields = ("subject", "message", "company__name")
