"""Optional sample menu for a chosen restaurant; never runs automatically."""
from decimal import Decimal
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.inventory.models import Product, ProductCategory, Unit
from apps.modules.catalog import RESTAURANT_TYPES
from apps.tenants.models import Company
from apps.verticals.restaurant.models import RestaurantMenuItem, RestaurantProfile


SAMPLES = (
    ("Burgers", "Classic Burger", "BP-DEMO-BURGER", "22.00", "Juicy patty, lettuce and house sauce.", "burger"),
    ("Burgers", "Double Cheese Burger", "BP-DEMO-DOUBLE", "29.00", "Two patties with melted cheese and pickles.", "double"),
    ("Burgers", "Spicy Chicken Burger", "BP-DEMO-SPICY", "25.00", "Crispy chicken with a spicy creamy sauce.", "spicy"),
    ("Breakfast", "Egg Breakfast Muffin", "BP-DEMO-MUFFIN", "14.00", "Warm muffin with egg and cheese.", "muffin"),
    ("Breakfast", "Honey Pancakes", "BP-DEMO-PANCAKES", "17.00", "Soft pancakes served with honey.", "pancakes"),
    ("Chicken", "Crispy Chicken Tenders", "BP-DEMO-TENDERS", "24.00", "Golden chicken strips with dip.", "tenders"),
    ("Chicken", "Chicken Bites", "BP-DEMO-BITES", "16.00", "Bite sized crispy chicken pieces.", "bites"),
    ("Sides", "Golden Fries", "BP-DEMO-FRIES", "9.00", "Crispy fries with sea salt.", "fries"),
    ("Sides", "Loaded Cheese Fries", "BP-DEMO-LOADED", "16.00", "Fries with warm cheese sauce.", "loaded"),
    ("Pizza", "Cheese Pizza", "BP-DEMO-PIZZA", "29.00", "Oven baked with tomato and melted cheese.", "pizza"),
    ("Pizza", "Vegetable Pizza", "BP-DEMO-VEGPIZZA", "32.00", "Oven baked with peppers and fresh vegetables.", "vegpizza"),
    ("Wraps", "Garden Wrap", "BP-DEMO-WRAP", "18.00", "Fresh vegetables wrapped to order.", "wrap"),
    ("Wraps", "Grilled Chicken Wrap", "BP-DEMO-CHICKENWRAP", "22.00", "Grilled chicken and crunchy lettuce.", "chickenwrap"),
    ("Salads", "Garden Salad", "BP-DEMO-SALAD", "18.00", "Fresh seasonal greens and cherry tomatoes.", "salad"),
    ("Kids Meals", "Kids Burger Meal", "BP-DEMO-KIDSMEAL", "25.00", "Small burger with fries and a drink.", "kidsmeal"),
    ("Combo Meals", "Burger Combo Meal", "BP-DEMO-COMBO", "35.00", "Burger, fries and a refreshing drink.", "combo"),
    ("Desserts", "Berry Sundae", "BP-DEMO-SUNDAE", "13.00", "Creamy dessert with berry topping.", "sundae"),
    ("Desserts", "Chocolate Sundae", "BP-DEMO-CHOCSUNDAE", "14.00", "Soft dessert with chocolate drizzle.", "chocsundae"),
    ("Drinks", "Iced Cola", "BP-DEMO-DRINK", "7.00", "A cool refreshment for your meal.", "drink"),
    ("Drinks", "Fresh Lemonade", "BP-DEMO-LEMONADE", "10.00", "Refreshing lemonade served cold.", "lemonade"),
)



class Command(BaseCommand):
    help = "Add 20 illustrated sample dishes to one restaurant: seed_restaurant_demo --company-slug SLUG"

    def add_arguments(self, parser):
        parser.add_argument("--company-slug", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        company = Company.objects.filter(slug=options["company_slug"]).first()
        if company is None or company.business_type.code not in RESTAURANT_TYPES:
            raise CommandError("Choose an existing restaurant, cafe or cafeteria company slug.")
        unit, _ = Unit.objects.for_company(company).get_or_create(name="pcs", defaults={"company": company})
        for category_name, name, sku, price, description, image_name in SAMPLES:
            category, _ = ProductCategory.objects.for_company(company).get_or_create(name=category_name, defaults={"company": company})
            product, _ = Product.objects.for_company(company).get_or_create(
                sku=sku, defaults={"company": company, "name": name, "category": category, "unit": unit,
                                   "selling_price": Decimal(price), "is_stock_tracked": False, "tracking_type": "none"})
            menu, _ = RestaurantMenuItem.objects.for_company(company).get_or_create(
                product=product, defaults={"company": company, "description": description, "is_available": True, "is_featured": image_name in {"burger", "double", "pizza", "combo"},
                                          "is_vegetarian": image_name in {"pancakes", "fries", "loaded", "pizza", "vegpizza", "wrap", "salad", "sundae", "chocsundae", "drink", "lemonade"}})
            if not menu.image:
                image_path = Path(__file__).resolve().parents[5] / "static" / "restaurant" / "demo" / f"{image_name}.png"
                menu.image.save(f"demo/{company.slug}/{image_name}.png", ContentFile(image_path.read_bytes()), save=True)
        self.stdout.write(self.style.SUCCESS("Sample menu ready. Illustrations are demo assets; edit dishes and prices before selling."))
