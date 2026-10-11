from django.db import models
from apps.tenants.models import TenantScopedModel


class SportsProductDetail(TenantScopedModel):
    """
    Deliberately thin, same reasoning as apps.verticals.textile.FabricDetail:
    Brands, Categories, Inventory, Sales, and Purchases (Phase 1 Section 12's
    list for this vertical) are already fully covered by apps.inventory —
    this only adds the couple of attributes that are genuinely sports-shop-
    specific. A shop selling the same shoe in multiple sizes is expected to
    create one inventory.Product per size (own SKU, own stock count) rather
    than modeling sizes as a sub-table here — that keeps stock tracking on
    the single ledger everything else already uses.
    """
    SPORT_CATEGORY = [
        ("cricket", "Cricket"), ("football", "Football"), ("badminton", "Badminton"),
        ("gym_equipment", "Gym Equipment"), ("running", "Running"), ("other", "Other"),
    ]
    GENDER = [("men", "Men"), ("women", "Women"), ("unisex", "Unisex"), ("kids", "Kids")]

    product = models.OneToOneField(
        "inventory.Product", on_delete=models.CASCADE, related_name="sports_detail",
    )
    sport_category = models.CharField(max_length=20, choices=SPORT_CATEGORY, default="other")
    size = models.CharField(max_length=20, blank=True)  # "9", "M", "42", ...
    gender = models.CharField(max_length=10, choices=GENDER, default="unisex")
    material = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.product.name} ({self.get_sport_category_display()})"


class TeamOrder(TenantScopedModel):
    """A club, school or company ordering jerseys with each player's name, number and size printed."""
    STATUS = [("new", "New"), ("printing", "Printing"), ("ready", "Ready"), ("delivered", "Delivered"),
              ("cancelled", "Cancelled")]
    team_name = models.CharField(max_length=150)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="team_orders")
    contact_phone = models.CharField(max_length=30, blank=True)
    item = models.CharField(max_length=150, help_text="e.g. Home jersey – blue, with shorts")
    price_per_piece = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField()
    status = models.CharField(max_length=12, choices=STATUS, default="new")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "-id"]

    def __str__(self):
        return f"{self.team_name} – {self.item}"

    @property
    def pieces(self):
        return self.players.count()

    @property
    def total(self):
        return self.price_per_piece * self.pieces

    @property
    def balance(self):
        return self.total - self.advance


class TeamOrderPlayer(TenantScopedModel):
    order = models.ForeignKey(TeamOrder, on_delete=models.CASCADE, related_name="players")
    name = models.CharField(max_length=60, blank=True)
    number = models.CharField(max_length=6, blank=True)
    size = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["id"]
