# BookPilot Boutique Edition

This build adds a dedicated **Ladies Fashion / Boutique** business type and the retail workflows needed by a small ladies-dress shop.

## Included

- Boutique product fields: Size, Colour, Material and Design
- Separate stock tracking for every product variant (for example, Black / XL)
- Existing SKU barcode generation and label printing retained
- POS barcode scan auto-adds the exact SKU to the cart
- Cash, Card and Bank payment choices for general expenses
- Daily and monthly sales report filters
- Cost of goods and gross-profit summary
- Top-selling product, category, size and colour reports
- Boutique business type enabled with the core modules during platform seeding

## Existing installation upgrade

Run the normal database migration after replacing the application files:

```bash
python manage.py migrate
```

If the platform reference data has already been created, run the idempotent seed command once to add the new boutique business type:

```bash
python manage.py seed_platform
```

## Barcode workflow

Assign a unique SKU to each size/colour variant, print the barcode from the product area, and scan it while the POS search field is active. An exact in-stock SKU is added to the cart automatically.
