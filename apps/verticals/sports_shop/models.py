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
