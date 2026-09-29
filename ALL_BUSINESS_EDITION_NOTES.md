# BookPilot All-Business Edition

## Complete business-type coverage audit (September 2026)

- All 108 registration business types now have an explicit, test-enforced workflow profile.
- Retail product masters now include missing boutique/clothing, general retail, wholesale,
  trading, import/export and industrial fields.
- Service records automatically default to the correct subject type (patient, student, pet,
  vehicle, asset or organization) and use matching identifier labels.
- Project-suite navigation and forms now adapt terminology for campaigns, engagements, events,
  properties, transport/delivery jobs, facilities, vendors, freelancers, drivers and carriers.
- The full regression suite contains 362 passing tests, including catalogue/profile coverage.

## Business catalogue and provisioning

- One canonical catalogue now drives all registration choices.
- The catalogue includes 108 business types: 12 dedicated, 46 retail/POS,
  33 service/work-order and 17 project/operations businesses.
- Every business type is seeded in advance and receives Accounting, Customers, Suppliers, Inventory, Sales, Purchases and Expenses.
- Retail, service and project clients receive their matching suite module.
- Unknown business types use a safe generic-business menu instead of incorrectly opening Mobile Shop.
- General Retail and Ladies Fashion / Boutique have explicit retail navigation.

## Retail suite

All retail clients share barcode POS, purchases, suppliers, stock, returns, expenses, accounting, customers, branches, reports and CSV import/export. Product forms add business-specific fields where relevant:

- Books: ISBN, author, publisher, grade/subject
- Perfume: fragrance family, volume and concentration
- Watches: model, movement, strap and water resistance
- Jewellery: weight, purity, stones and making charge
- Spare parts: part/OEM number and compatible models
- Car showroom: VIN, chassis, year, transmission and mileage
- Electronics/computers/equipment: model, serial tracking, warranty and specifications
- Bakery/grocery/supermarket: production/expiry, ingredients, allergens, pack and origin
- Cosmetics, pets, flowers, furniture, hardware, printing and manufacturing-specific attributes
- Wholesale price and carton quantity across the retail suite
- Restaurant/cafeteria and café menu attributes, including item type,
  preparation time, ingredients and allergens
- Footwear, baby products, toys/gifts, appliances, electrical/plumbing,
  building materials, tyres/batteries, fresh food, e-commerce, mobile
  accessories, uniforms, kitchenware, musical instruments and agricultural
  supplies
- Optical product attributes and fuel grade/tank/density fields

Industry attributes are retained in product CSV export/import through the `Attributes JSON` column.

## Service suite

For clinics, physiotherapy, veterinary, tuition, driving school, studio,
consultancy, garage, repair, home service, laundry, catering, rentals, hotels,
nursery/school, travel, laboratories, legal/insurance, pest control, moving,
maintenance, nursing, document clearing, brokerage, halls and co-working:

- Customer plus patient/student/pet/vehicle/asset/organization profiles
- Reference identifiers and configurable structured details
- Cases/work orders with assignment, status, due dates and history
- Diagnosis/lesson/repair/follow-up notes
- Services, staff and appointments
- Multi-session service packages with invoicing and balance tracking
- Case, appointment revenue and follow-up reports
- Suite access restricted to matching business types

## Project suite

For construction, agencies, IT/software, accounting, recruitment, security,
events, cleaning, maintenance, landscaping, property/facility management,
logistics/transport, courier/delivery and interior design:

- Projects, clients, budgets, contract value and expenses
- Contractors and project profitability
- Milestones with value and progress
- Tasks with staff assignment, priority, due date and status
- Timesheets, hourly rates and labour cost
- Project and suite access restricted to matching business types

## Dedicated vertical improvements

- Mobile Shop: complete IMEI POS, warranty, repairs, trade-in, instalments and reports
- Boutique: structured variants and dedicated retail navigation
- Gym: plans, enrollment, invoicing, attendance, renewal, freeze/unfreeze and reports
- Spa/Saloon/Beauty: services, staff, appointments, packages, commissions and reports
- Textile: fabrics, measurements, tailoring orders and reports
- Vehicle Wash: vehicles, packages, work status, invoicing and reports
- Cycle Shop: serial units, sales and service tickets
- Medical/Protein shops: batches, expiry, sales/dispensing and alerts
- Construction/agency: expanded project work management
- Restaurant/Café/Catering: dining areas and tables, dine-in/takeaway/delivery
  orders, waiter assignment, menu modifiers, combos, recipe-based ingredient
  consumption, KOT/kitchen display statuses, hold/resume, split/merge orders,
  split payments, service charge/tips/discounts, delivery assignment and
  shift cash reconciliation
- Delivery integrations: encrypted Talabat, Snoonu, Rafeeq, Deliveroo or
  custom-provider credentials; Store ID, test/live mode, commission and
  auto-accept settings; signed webhook endpoint, idempotent external-order
  import, SKU mapping and import/error history

## Upgrade

```bash
python manage.py migrate
python manage.py seed_platform
```
