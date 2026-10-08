"""Excel / CSV product import with a template made for each business type.

The template has the columns that business needs (sizes, colours and gender for a boutique, expiry for a
pharmacy, warranty for electronics…) and a few example rows from its sample kit, so the owner can copy their own
list over the examples and upload it.
"""
import csv
import io
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.modules.catalog import ALIASES, billing_mode, business_features, business_group

BASE = ["SKU", "Name", "Category", "Brand", "Unit", "Cost Price", "Selling Price", "Opening Stock", "Reorder Level"]
VARIANT_TYPES = {"clothing_store", "ladies_fashion_boutique", "footwear_store", "uniform_shop", "sports_shop", "textile",
                 "baby_products_store", "ecommerce_store", "cycle_shop"}
GENDER_TYPES = VARIANT_TYPES | {"perfume_shop", "watch_shop", "cosmetics_store", "optical_shop", "saloon",
                                "beauty_parlour", "gym"}
YES = {"yes", "y", "true", "1", "x", "✓"}


def _code(company):
    code = company.business_type.code
    return ALIASES.get(code, code)


def _industry_fields(code):
    from .forms import BusinessProductForm
    labels = BusinessProductForm.FIELD_LABELS
    return [(key, labels[key]) for key in BusinessProductForm.INDUSTRY_FIELDS.get(code, ()) if key in labels]


def columns(company):
    code = _code(company)
    cols = list(BASE)
    if billing_mode(code) or business_group(code) in ("service", "project"):
        cols.append("Service (yes/no)")
    if code in VARIANT_TYPES:
        cols += ["Size", "Colour", "Variant of (SKU)"]
    if code == "textile":
        cols += ["Material", "Design"]
    attr_labels = [label for key, label in _industry_fields(code) if key != "gender"]
    if code in GENDER_TYPES or any(k == "gender" for k, _ in _industry_fields(code)):
        cols.append("Gender")
    cols += attr_labels
    if "weighed" in business_features(code):
        cols += ["Sold by weight (yes/no)", "Scale code"]
    return cols


def _attr_keys(company):
    keys = {label: key for key, label in _industry_fields(_code(company))}
    keys["Gender"] = "gender"
    return keys


def example_rows(company):
    """A few rows from this business type's sample kit, in template column order."""
    from apps.industry.sample_kit import kit_for
    cols = columns(company)
    kit = kit_for(_code(company))
    labels = {v: k for k, v in _attr_keys(company).items()}
    rows, n = [], 0

    def row(item, sku, *, service=False, size="", colour="", parent="", stock=""):
        attrs = item.get("attrs") or {}
        price = Decimal(str(item["price"]))
        values = {"SKU": sku, "Name": item["name"], "Category": item["category"], "Brand": item.get("brand", ""),
                  "Unit": "service" if service else item.get("unit", "pcs"),
                  "Cost Price": "" if service else f"{price * Decimal('0.6'):.2f}", "Selling Price": f"{price:.2f}",
                  "Opening Stock": "" if service else stock, "Reorder Level": "" if service else 2,
                  "Service (yes/no)": "yes" if service else "no", "Size": size or attrs.get("size", ""),
                  "Colour": colour or attrs.get("colour", ""), "Variant of (SKU)": parent,
                  "Material": attrs.get("material", ""), "Design": attrs.get("design", ""),
                  "Sold by weight (yes/no)": "yes" if attrs.get("sold_by_weight") else "no",
                  "Scale code": ""}
        for key, value in attrs.items():
            if key in labels:
                values[labels[key]] = value
        rows.append([values.get(c, "") for c in cols])

    for item in kit["products"][:3]:
        n += 1
        row(item, f"ITEM-{n:03d}", stock=item.get("stock", 10))
    for item in kit["variants"][:1]:
        n += 1
        parent = f"ITEM-{n:03d}"
        row(item, parent)
        for size in item["sizes"][:2]:
            n += 1
            row(item, f"ITEM-{n:03d}", size=size, colour=(item["colours"] or [""])[0], parent=parent, stock=item["stock"])
    for item in kit["services"][:2]:
        n += 1
        row(item, f"SRV-{n:03d}", service=True)
    if not rows:  # restaurants: a few dishes from the Kerala menu kit
        from apps.verticals.restaurant import kerala_menu
        for category, _station in kerala_menu.CATEGORIES[:3]:
            dish = kerala_menu.DISHES[category][0]
            n += 1
            row({"name": dish[1], "category": category, "price": dish[3], "unit": "plate"}, f"ITEM-{n:03d}", stock="")
    return rows


def read(upload):
    """Rows of dicts from an uploaded .xlsx or .csv. Raises ValueError with a message to show."""
    data = upload.read()
    name = (upload.name or "").lower()
    if name.endswith(".xlsx") or data[:2] == b"PK":
        from . import xlsx
        try:
            grid = xlsx.read_rows(data)
        except Exception:
            raise ValueError("Couldn't read that Excel file. Save it as .xlsx (or CSV) and try again.")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
        grid = list(csv.reader(io.StringIO(text)))
    grid = [r for r in grid if any((c or "").strip() for c in r)]
    if not grid:
        raise ValueError("The file is empty.")
    header = [(h or "").strip() for h in grid[0]]
    return [dict(zip(header, [(c or "").strip() for c in r])) for r in grid[1:]], header


def _number(value, kind=Decimal):
    value = (value or "").replace(",", "").strip()
    if not value:
        return kind(0)
    return kind(Decimal(value)) if kind is int else kind(value)


@transaction.atomic
def import_rows(company, rows):
    """Creates or updates products by SKU. Returns (created, updated, errors)."""
    from apps.inventory.models import Brand, Product, ProductCategory, StockMovement, Unit, Warehouse
    attr_keys = _attr_keys(company)
    warehouse = Warehouse.objects.filter(company=company, is_default=True).first() or \
        Warehouse.objects.filter(company=company).first()
    created = updated = 0
    errors = []
    parents = []
    for i, row in enumerate(rows, start=2):
        sku, name = row.get("SKU", ""), row.get("Name", "")
        if not sku or not name:
            errors.append(f"Row {i}: SKU and Name are required.")
            continue
        try:
            selling, cost = _number(row.get("Selling Price")), _number(row.get("Cost Price"))
            reorder, stock = _number(row.get("Reorder Level"), int), _number(row.get("Opening Stock"))
        except (InvalidOperation, ValueError):
            errors.append(f"Row {i}: a price, stock or reorder level is not a number.")
            continue
        service = (row.get("Service (yes/no)") or "").lower() in YES
        unit, _ = Unit.objects.get_or_create(company=company, name=row.get("Unit") or ("service" if service else "pcs"))
        category = ProductCategory.objects.get_or_create(company=company, name=row["Category"])[0] \
            if row.get("Category") else None
        brand = Brand.objects.get_or_create(company=company, name=row["Brand"])[0] if row.get("Brand") else None
        try:
            attributes = json.loads(row.get("Attributes JSON") or "{}")
            if not isinstance(attributes, dict):
                raise ValueError
        except ValueError:
            errors.append(f"Row {i}: Attributes JSON must be a JSON object.")
            continue
        for label, key in attr_keys.items():
            if row.get(label):
                attributes[key] = row[label]
        if (row.get("Sold by weight (yes/no)") or "").lower() in YES:
            attributes["sold_by_weight"] = True
        if row.get("Scale code"):
            attributes["scale_code"] = row["Scale code"]
        existing = Product.objects.filter(company=company, sku=sku).first()
        product, was_created = Product.objects.update_or_create(company=company, sku=sku, defaults={
            "name": name, "unit": unit, "category": category, "brand": brand, "cost_price": cost,
            "selling_price": selling, "reorder_level": reorder, "is_stock_tracked": not service,
            "tracking_type": "none" if service else (existing.tracking_type if existing else "basic"),
            "size": row.get("Size", ""), "colour": row.get("Colour", ""), "material": row.get("Material", ""),
            "design": row.get("Design", ""), "attributes": {**((existing.attributes or {}) if existing else {}), **attributes},
        })
        created += was_created
        updated += not was_created
        if was_created and stock and not service and warehouse:
            StockMovement.objects.create(company=company, product=product, warehouse=warehouse, quantity=stock,
                                         reason="adjustment", reference="Opening stock (import)")
        if row.get("Variant of (SKU)"):
            parents.append((i, product, row["Variant of (SKU)"]))
    for i, product, parent_sku in parents:  # after all rows, so a parent can come later in the file
        parent = Product.objects.filter(company=company, sku=parent_sku).exclude(pk=product.pk).first()
        if parent is None:
            errors.append(f"Row {i}: no product with SKU {parent_sku} to be a variant of.")
            continue
        product.parent = parent
        product.variant_label = ""
        product.save()
    return created, updated, errors
