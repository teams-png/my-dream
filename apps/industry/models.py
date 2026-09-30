from django.conf import settings
from django.db import models

from apps.tenants.models import TenantScopedModel

RATE_UNITS = [("hour", "Per hour"), ("day", "Per day"), ("night", "Per night"), ("month", "Per month"),
              ("event", "Per booking")]


# ----------------------------------------------------------------- bookings

class BookableResource(TenantScopedModel):
    """A room, vehicle, piece of equipment, hall or desk that customers book by time."""
    KINDS = [("room", "Room"), ("vehicle", "Vehicle"), ("equipment", "Equipment"), ("hall", "Hall"),
             ("space", "Space / desk"), ("other", "Other")]
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KINDS, default="other")
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rate_unit = models.CharField(max_length=8, choices=RATE_UNITS, default="day")
    capacity = models.PositiveSmallIntegerField(default=1, help_text="Guests / seats (0 = not relevant).")
    details = models.CharField(max_length=255, blank=True, help_text="e.g. plate number, floor, size, features.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    product = models.ForeignKey("inventory.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                help_text="Service product used on invoices; created automatically.")

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Booking(TenantScopedModel):
    STATUS = [("reserved", "Reserved"), ("checked_in", "Checked in"), ("completed", "Completed"),
              ("cancelled", "Cancelled"), ("no_show", "No-show")]
    ACTIVE = ("reserved", "checked_in")
    number = models.CharField(max_length=20, blank=True)
    resource = models.ForeignKey(BookableResource, on_delete=models.PROTECT, related_name="bookings")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="bookings")
    start = models.DateTimeField()
    end = models.DateTimeField()
    guests = models.PositiveSmallIntegerField(default=1)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    rate_unit = models.CharField(max_length=8, choices=RATE_UNITS)
    advance = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                  help_text="Paid in advance; applied to the invoice at check-out.")
    advance_method = models.CharField(max_length=10, default="cash")
    advance_date = models.DateField(null=True, blank=True)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                           help_text="Refundable; held and returned, not income.")
    deposit_returned = models.BooleanField(default=False)
    extras = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extras_note = models.CharField(max_length=255, blank=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=STATUS, default="reserved")
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start"]
        indexes = [models.Index(fields=["company", "resource", "start"]), models.Index(fields=["company", "status"])]

    def __str__(self):
        return self.number or f"Booking {self.pk}"
