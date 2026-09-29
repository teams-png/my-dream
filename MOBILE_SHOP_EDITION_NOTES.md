# BookPilot Mobile Shop Edition

This build includes a complete mobile-retail workflow on top of BookPilot accounting.

## Mobile shop features

1. Handsets, accessories, spare parts and repair-service products
2. Structured mobile specifications: model number, RAM, storage, network and battery
3. IMEI/serial-wise stock with new, used and refurbished conditions
4. Bulk IMEI intake with optional supplier purchase posting
5. Combined POS billing for IMEI handsets and normal accessories
6. SKU, barcode, IMEI and serial scanning at POS
7. Cash, card, bank, credit and instalment sales
8. Customer credit-limit validation, dues and instalment collection
9. Warranty expiry printed on invoices and warranty-claim tracking
10. Repair job cards with technician, status, labour, spare parts and repair invoices
11. Trade-in/exchange workflow that creates a purchase and adds the used handset to stock
12. Date-filtered revenue, COGS, gross profit, stock value, repair, warranty and dues reports

## Upgrade an existing installation

```bash
python manage.py migrate
python manage.py seed_platform
```

Create handset products with **Item type = Mobile Handset**. Add IMEIs from **Mobile Shop → IMEI Purchase**. Accessories and spare parts continue to use normal quantity stock. At POS, scanning an IMEI selects that exact handset; SKU scanning selects a normal product or prompts for an available handset IMEI.
