from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.tenants.models import TenantScopedModel


class DiningArea(TenantScopedModel):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "name")

    def __str__(self): return self.name


class RestaurantProfile(TenantScopedModel):
    public_menu_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    tagline = models.CharField(max_length=180, blank=True)
    opening_hours = models.CharField(max_length=180, blank=True)
    delivery_minimum = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    qr_ordering_enabled = models.BooleanField(default=False)
    service_charge_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 help_text="Suggested service charge for dine-in bills (%).")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                      help_text="VAT/GST charged on restaurant bills (%). 0 = no tax.")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company"], name="one_restaurant_profile_per_company")]


class DiningTable(TenantScopedModel):
    STATUS = [("available", _("Available")), ("occupied", _("Occupied")), ("reserved", _("Reserved")), ("cleaning", _("Cleaning"))]
    area = models.ForeignKey(DiningArea, on_delete=models.CASCADE, related_name="tables")
    name = models.CharField(max_length=50)
    capacity = models.PositiveSmallIntegerField(default=4)
    status = models.CharField(max_length=12, choices=STATUS, default="available")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "name")

    def __str__(self): return f"{self.area.name} / {self.name}"


class MenuModifier(TenantScopedModel):
    name = models.CharField(max_length=100)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self): return self.name


class MenuModifierGroup(TenantScopedModel):
    name = models.CharField(max_length=100)
    min_selections = models.PositiveSmallIntegerField(default=0)
    max_selections = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self): return self.name


class RestaurantMenuItem(TenantScopedModel):
    """Restaurant-only presentation and availability data for a Product."""
    SPICE_LEVELS = [
        ("none", "Not spicy"), ("mild", "Mild"),
        ("medium", "Medium"), ("hot", "Hot"),
    ]

    product = models.OneToOneField(
        "inventory.Product", on_delete=models.CASCADE, related_name="restaurant_menu_item"
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="restaurant/menu/%Y/%m/", blank=True)
    preparation_minutes = models.PositiveSmallIntegerField(default=10)
    spice_level = models.CharField(max_length=10, choices=SPICE_LEVELS, default="none")
    is_vegetarian = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    available_from = models.TimeField(null=True, blank=True)
    available_until = models.TimeField(null=True, blank=True)
    modifier_groups = models.ManyToManyField(MenuModifierGroup, blank=True, related_name="menu_items")

    class Meta:
        ordering = ["sort_order", "product__name"]

    def __str__(self):
        return self.product.name

    def is_orderable_now(self, at_time=None):
        if not self.is_available or not self.product.is_active:
            return False
        at_time = at_time or timezone.localtime().time()
        if self.available_from and self.available_until:
            if self.available_from <= self.available_until:
                return self.available_from <= at_time <= self.available_until
            return at_time >= self.available_from or at_time <= self.available_until
        if self.available_from and at_time < self.available_from:
            return False
        if self.available_until and at_time > self.available_until:
            return False
        return True

    def food_cost(self):
        return sum((x.quantity * x.ingredient_product.cost_price for x in self.product.restaurant_recipe.all()), Decimal("0"))


class MenuModifierOption(TenantScopedModel):
    group = models.ForeignKey(MenuModifierGroup, on_delete=models.CASCADE, related_name="options")
    modifier = models.ForeignKey(MenuModifier, on_delete=models.CASCADE, related_name="group_options")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("group", "modifier")
        ordering = ["sort_order", "modifier__name"]


class KitchenStation(TenantScopedModel):
    name = models.CharField(max_length=100)
    categories = models.ManyToManyField("inventory.ProductCategory", blank=True, related_name="kitchen_stations")
    colour = models.CharField(max_length=20, default="#f97316")
    is_active = models.BooleanField(default=True)

    def __str__(self): return self.name


class TableReservation(TenantScopedModel):
    STATUS = [("booked", _("Booked")), ("seated", _("Seated")), ("completed", _("Completed")), ("cancelled", _("Cancelled")), ("no_show", _("No-show"))]
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    reservation_at = models.DateTimeField()
    guest_count = models.PositiveSmallIntegerField(default=2)
    table = models.ForeignKey(DiningTable, null=True, blank=True, on_delete=models.SET_NULL, related_name="reservations")
    status = models.CharField(max_length=12, choices=STATUS, default="booked")
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["reservation_at"]


class FoodWaste(TenantScopedModel):
    REASONS = [("expired", "Expired"), ("spoiled", "Spoiled"), ("preparation", "Preparation waste"), ("customer_return", "Customer return"), ("other", "Other")]
    ingredient = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="restaurant_waste")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=20, choices=REASONS)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="restaurant_waste_recorded")
    recorded_at = models.DateTimeField(auto_now_add=True)


class RecipeIngredient(TenantScopedModel):
    menu_product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE, related_name="restaurant_recipe")
    ingredient_product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="restaurant_ingredient_in")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)

    class Meta:
        unique_together = ("company", "menu_product", "ingredient_product")


class RestaurantCombo(TenantScopedModel):
    name = models.CharField(max_length=150)
    billing_product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT, related_name="restaurant_combos")
    is_active = models.BooleanField(default=True)


class RestaurantComboItem(TenantScopedModel):
    combo = models.ForeignKey(RestaurantCombo, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1)


class RestaurantShift(TenantScopedModel):
    STATUS = [("open", _("Open")), ("closed", _("Closed"))]
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="restaurant_shifts_opened")
    opened_at = models.DateTimeField(auto_now_add=True)
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="restaurant_shifts_closed")
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="open")


class RestaurantOrder(TenantScopedModel):
    CHANNELS = [("dine_in", _("Dine-in")), ("takeaway", _("Takeaway")), ("delivery", _("Delivery"))]
    STATUS = [("draft", _("Draft")), ("held", _("Held")), ("kitchen", _("Sent to kitchen")), ("ready", _("Ready")), ("served", _("Served")), ("paid", _("Paid")), ("cancelled", _("Cancelled"))]
    order_number = models.CharField(max_length=30)
    channel = models.CharField(max_length=12, choices=CHANNELS)
    table = models.ForeignKey(DiningTable, null=True, blank=True, on_delete=models.PROTECT, related_name="orders")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT)
    waiter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="restaurant_orders")
    shift = models.ForeignKey(RestaurantShift, null=True, blank=True, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=12, choices=STATUS, default="draft")
    guests = models.PositiveSmallIntegerField(default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    delivery_address = models.TextField(blank=True)
    delivery_phone = models.CharField(max_length=30, blank=True)
    delivery_driver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="restaurant_deliveries")
    reservation = models.ForeignKey(TableReservation, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    public_order_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    cancelled_reason = models.CharField(max_length=255, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="restaurant_orders_cancelled")
    cancelled_at = models.DateTimeField(null=True, blank=True)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tip_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    invoice = models.OneToOneField("sales.SalesInvoice", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "order_number")
        ordering = ["-created_at"]

    @property
    def subtotal(self):
        return sum((line.total for line in self.lines.all()), Decimal("0"))

    @property
    def tax_amount(self):
        taxable = self.subtotal + self.service_charge + self.tip_amount
        return (taxable * self.tax_percent / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def total(self):
        return self.subtotal + self.service_charge + self.tip_amount + self.tax_amount - self.discount_amount

    @property
    def unsent_lines(self):
        return [line for line in self.lines.all() if line.sent_at is None]


class RestaurantOrderLine(TenantScopedModel):
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("inventory.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)
    # Kitchen round this line was sent in (1 = first KOT). 0 with sent_at set means
    # it was sent as part of another order that has since been merged in.
    kitchen_round = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)

    @property
    def modifier_total(self):
        return sum((m.price_delta for m in self.modifiers.all()), Decimal("0"))

    @property
    def total(self):
        return self.quantity * (self.unit_price + self.modifier_total)


class RestaurantOrderLineModifier(TenantScopedModel):
    line = models.ForeignKey(RestaurantOrderLine, on_delete=models.CASCADE, related_name="modifiers")
    modifier = models.ForeignKey(MenuModifier, on_delete=models.PROTECT)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2)


class KitchenTicket(TenantScopedModel):
    STATUS = [("queued", _("Queued")), ("preparing", _("Preparing")), ("ready", _("Ready")), ("served", _("Served"))]
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name="kitchen_tickets")
    station = models.ForeignKey(KitchenStation, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets")
    ticket_number = models.CharField(max_length=30)
    kitchen_round = models.PositiveSmallIntegerField(default=1)
    priority = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS, default="queued")
    printed_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("company", "ticket_number")


class RestaurantPaymentSplit(TenantScopedModel):
    METHODS = [("cash", "Cash"), ("card", "Card"), ("bank", "Bank")]
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name="payment_splits")
    method = models.CharField(max_length=10, choices=METHODS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)


class DeliveryIntegration(TenantScopedModel):
    PROVIDERS = [("talabat", "Talabat"), ("snoonu", "Snoonu"), ("rafeeq", "Rafeeq"),
                 ("deliveroo", "Deliveroo"), ("custom", "Custom Provider")]
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    webhook_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    display_name = models.CharField(max_length=100, blank=True)
    store_id = models.CharField(max_length=150)
    api_base_url = models.URLField(blank=True)
    api_key_ciphertext = models.TextField(blank=True)
    api_secret_ciphertext = models.TextField(blank=True)
    webhook_secret_ciphertext = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=False)
    test_mode = models.BooleanField(default=True)
    auto_accept_orders = models.BooleanField(default=False)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        unique_together = ("company", "provider", "store_id")

    def set_secret(self, name, value):
        from apps.platform_admin.payment_gateways import encrypt_credential
        setattr(self, f"{name}_ciphertext", encrypt_credential(value) if value else "")

    def get_secret(self, name):
        from apps.platform_admin.payment_gateways import decrypt_credential
        value = getattr(self, f"{name}_ciphertext", "")
        return decrypt_credential(value) if value else ""


class DeliveryOrderImport(TenantScopedModel):
    STATUS = [("received", "Received"), ("imported", "Imported"), ("rejected", "Rejected"), ("failed", "Failed")]
    integration = models.ForeignKey(DeliveryIntegration, on_delete=models.PROTECT, related_name="order_imports")
    external_order_id = models.CharField(max_length=150)
    status = models.CharField(max_length=12, choices=STATUS, default="received")
    restaurant_order = models.ForeignKey(RestaurantOrder, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("integration", "external_order_id")
        ordering = ["-received_at"]
