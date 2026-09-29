# Phase 26 (part 1 of 3) — Invoice-linkage gap: the 4 "already has a Product FK" verticals

Corrects PHASE25_NOTES.md's count: it's 8 verticals with an unwired
`create_invoice()` TODO, not 6 — `beauty_parlour` and `mobile_shop` have
the identical gap but weren't named in the original list. Splitting the
fix into three reviewable chunks by shape, same reasoning Phase 22/23
split gym and spa into separate phases rather than doing all verticals
at once. This part does the four that already have a `product` FK to
`inventory.Product` and just needed the invoice call wired in:
**mobile_shop, cycle_shop, medical_shop, protein_shop.**

Still open, next phases:
- **saloon, beauty_parlour** — same Appointment/ServicePackage shape as
  spa, but (unlike spa) their `SaloonService`/`BeautyService`/
  `ServicePackage` models have no `product` FK at all yet — needs a
  migration plus `create_saloon_service()`/`create_service_package()`
  factories mirroring `spa.services`, before `book_appointment()` and
  `purchase_package()` can invoice.
- **textile, vehicle_wash** — no product concept at all (a tailoring
  order's price is custom per order; a wash package has no linked
  Product either). Needs a shared per-company "service" Product
  convention decided and built, not just a wiring change.

## Drop-in files (same paths as your existing project root)

```
apps/customers/services.py                                    (modified — new helper)
apps/verticals/mobile_shop/services.py                          (modified)
apps/verticals/mobile_shop/views.py                              (modified)
apps/verticals/mobile_shop/tests/__init__.py                    (new)
apps/verticals/mobile_shop/tests/test_invoicing.py               (new)
apps/verticals/cycle_shop/services.py                            (modified)
apps/verticals/cycle_shop/serializers.py                         (modified)
apps/verticals/cycle_shop/views.py                               (modified)
apps/verticals/cycle_shop/tests/__init__.py                      (new)
apps/verticals/cycle_shop/tests/test_invoicing.py                 (new)
apps/verticals/medical_shop/services.py                          (modified)
apps/verticals/medical_shop/serializers.py                       (modified)
apps/verticals/medical_shop/views.py                             (modified)
apps/verticals/medical_shop/tests/__init__.py                    (new)
apps/verticals/medical_shop/tests/test_invoicing.py               (new)
apps/verticals/protein_shop/services.py                          (modified)
apps/verticals/protein_shop/serializers.py                       (modified)
apps/verticals/protein_shop/views.py                              (modified)
apps/verticals/protein_shop/tests/__init__.py                     (new)
apps/verticals/protein_shop/tests/test_invoicing.py                (new)
```

Run `python manage.py check` after dropping these in — no new migrations
(all four Products already existed; nothing about their schema changed).

## 1. Shared walk-in customer helper (`apps.customers.services.get_or_create_walkin_customer`)

All four verticals let the buyer/customer field on a sale be optional
(genuine over-the-counter sales), but `SalesInvoice.customer` has no
`null=True` — every invoice must be attributable to someone. Added one
shared helper, used by all four, rather than each growing its own
"walk-in customer" convention: `get_or_create(company=company,
name="Walk-in Customer")`.

## 2. The fix, same shape in all four

`mobile_shop.sell_unit()` / `cycle_shop.sell_unit()` /
`medical_shop.dispense()` / `protein_shop.sell()` now:

1. Validate as before (unit in stock / batch not expired / quantity available).
2. Call `sales.services.create_invoice()` with the linked Product, using
   the walk-in customer if none was given.
3. Only then mutate the unit's status / decrement the batch's
   `quantity_remaining` and create the domain row.

All inside the existing `@transaction.atomic` — a failed invoice call
(e.g. a bad company setup missing chart-of-accounts) rolls back the whole
sale, same guarantee `gym.services.enroll_member` established.

Each vertical's action serializer (`SellUnitSerializer` /
`SellCycleUnitSerializer` / `DispenseActionSerializer` /
`SellActionSerializer`) gained a required `warehouse` field, scoped to
the company via `Warehouse.objects.for_company(company)` — which also
means a cross-tenant warehouse id is rejected by DRF's own field
validation (400) before the view ever runs, same protection
`EnrollMemberSerializer` gets from its queryset, no separate manual IDOR
check needed for this field.

## 3. Known accepted quirk (documented in each vertical's services.py, same as Phase 22/23's for gym/spa)

If the linked Product is `is_stock_tracked=True` (the default), the
invoice call also writes a `StockMovement` — which doesn't correspond to
real warehouse quantity for these verticals, since their unit of stock is
one IMEI/serial number or one batch, not a Product-level count (see each
model's own docstring). Not forced to `is_stock_tracked=False` here,
since some shops may deliberately also move these Products through the
generic Purchase flow and a blanket data change wasn't asked for — left
as a per-company decision, called out explicitly in each services.py
docstring, same as the existing gym/spa precedent.

## Verified

```
python manage.py check                    # 0 issues
python manage.py makemigrations --check   # clean
pytest                                     # 117 passed (104 from Phase 25 + 13 new)
```

---

# Phase 26 (part 2 of 3) — Invoice-linkage gap: saloon + beauty_parlour

Closes the second chunk of the 8-vertical gap — the two that needed a
schema migration first, since (unlike mobile_shop/cycle_shop/
medical_shop/protein_shop, part 1) `SaloonService`/`BeautyService`/
`ServicePackage` had no `product` FK to `inventory.Product` at all.

## Drop-in files (same paths as your existing project root)

```
apps/verticals/saloon/models.py                                  (modified — new product FK, migration 0002)
apps/verticals/saloon/services.py                                 (rewritten)
apps/verticals/saloon/serializers.py                               (rewritten)
apps/verticals/saloon/views.py                                     (rewritten)
apps/verticals/saloon/migrations/0002_saloonservice_product_servicepackage_product.py   (new)
apps/verticals/saloon/tests/__init__.py                            (new)
apps/verticals/saloon/tests/test_appointment_invoicing.py           (new)
apps/verticals/beauty_parlour/models.py                            (modified — same shape)
apps/verticals/beauty_parlour/services.py                           (rewritten)
apps/verticals/beauty_parlour/serializers.py                         (rewritten)
apps/verticals/beauty_parlour/views.py                               (rewritten)
apps/verticals/beauty_parlour/migrations/0002_beautyservice_product_servicepackage_product.py   (new)
apps/verticals/beauty_parlour/tests/__init__.py                      (new)
apps/verticals/beauty_parlour/tests/test_appointment_invoicing.py     (new)
apps/webapp/views.py                                                (modified — see below)
```

Run `python manage.py migrate` after dropping these in — two new
migrations (nullable FK additions, safe on existing data since both
fields are `null=True`).

## The fix — identical shape to spa (Phase 23), applied to both verticals

1. Added a nullable `product` OneToOneField to `SaloonService`/
   `BeautyService` and to their `ServicePackage`, plus `create_saloon_service()`
   / `create_beauty_service()` and `create_service_package()` factory
   functions that create the linked service Product
   (`is_stock_tracked=False`, same reasoning as spa's) in the same
   transaction as the service/package row.
2. `book_appointment()` now invoices a walk-in (no `customer_package`)
   via `sales.services.create_invoice()` before creating the Appointment;
   a package-covered appointment still doesn't invoice (already paid at
   purchase time) — identical branch logic to spa's.
3. `purchase_package()` now invoices the package price before creating
   the `CustomerPackage` row.
4. `complete_appointment()` unchanged — never invoices, for the same
   reason spa's doesn't.
5. Rewrote both verticals' `serializers.py`/`views.py` to match spa's
   pattern exactly: dedicated `Create*Serializer`s that route through the
   factory functions (so a service/package is never created without its
   Product), and `warehouse` added to the appointment/package-purchase
   serializers with the same tenant-scoped-queryset IDOR protection
   spa's `_idor_guard` uses.

## Also fixed: two webapp (Django-template) call sites Group 1 didn't need to touch

Group 1's four verticals only had a DRF API; saloon and beauty_parlour
also have a Django-template UI in `apps/webapp/views.py` that:

- Called `SaloonService.objects.create(...)` / `BeautyService.objects.create(...)`
  directly, bypassing the new factory functions entirely — every service
  created through the web UI would have had `product=None` forever, so
  the very first walk-in booking against it would hit the ValueError
  guard. Both now call `saloon_services.create_saloon_service()` /
  `beauty_services.create_beauty_service()` instead.
- Called `book_appointment()` without `user`/`warehouse` (didn't exist
  yet when this UI was written). Both now pass `user=request.user` and
  `warehouse=_default_warehouse(company)` — the same helper every other
  webapp view already uses for this (`apps/webapp/views.py` has ~7 other
  call sites using it).

No package-purchase UI exists yet for either vertical (API-only), so
there was nothing else to fix there.

## Verified

```
python manage.py check                    # 0 issues
python manage.py makemigrations --check   # clean
pytest                                     # 137 passed (117 before this phase + 20 new)
```

## Still open — next phase (part 3 of 3)

- **textile, vehicle_wash** — no product concept exists at all yet (a
  tailoring order's price is custom per order; a wash package has no
  linked Product either). Needs a shared "service product" convention
  designed, not just a wiring change like this phase's.
- CompanyCounter concurrency test, `general_retail` vertical decision,
  repo cruft cleanup — unchanged from earlier notes.

---

# Phase 26 (part 3 of 3) — Invoice-linkage gap: textile + vehicle_wash — the 8-vertical gap is now fully closed

Closes the last chunk. Unlike parts 1 and 2, neither vertical had any
product concept to link to at all — each needed its own small design
decision, not just wiring.

## Drop-in files

```
apps/verticals/textile/services.py                                  (rewritten)
apps/verticals/textile/serializers.py                                (rewritten)
apps/verticals/textile/views.py                                      (rewritten)
apps/verticals/textile/tests/__init__.py                             (new)
apps/verticals/textile/tests/test_order_invoicing.py                  (new)
apps/verticals/vehicle_wash/models.py                                (modified — new fields, migration 0002)
apps/verticals/vehicle_wash/services.py                               (rewritten)
apps/verticals/vehicle_wash/serializers.py                            (rewritten)
apps/verticals/vehicle_wash/views.py                                  (rewritten)
apps/verticals/vehicle_wash/migrations/0002_washorder_sales_invoice_washpackage_product.py   (new)
apps/verticals/vehicle_wash/tests/__init__.py                         (new)
apps/verticals/vehicle_wash/tests/test_wash_invoicing.py               (new)
apps/webapp/views.py                                                 (modified — see below)
```

Run `python manage.py migrate` — one new migration (vehicle_wash), both
fields nullable, safe on existing data.

## textile — one shared "Tailoring Service" placeholder Product, not one per order

A tailoring order's price is fully custom per order (labour, not a fixed
service list), so there's no finite set of "services" to pre-create
Products for the way spa/saloon/beauty_parlour do. Instead,
`_get_or_create_tailoring_service_product(company)` get-or-creates one
shared, `is_stock_tracked=False` Product per company (SKU
`TXT-TAILORING-SERVICE`), and `create_tailoring_order()` invoices the
order's own `price` as the line's `unit_price` — `create_invoice()` never
required `unit_price` to match the product's own `selling_price`, so one
placeholder Product can represent any custom-priced job. `TailoringOrder`
already had a `sales_invoice` field reserved for exactly this (visible in
the model back when this file was first written) — no migration needed
for textile.

## vehicle_wash — invoices on completion, not on booking

This vertical's own services.py docstring already said "a completed wash
is a sale" before this phase — so unlike every other vertical here,
`complete_wash()` is where the invoice happens, not `book_wash()`. A wash
that's only booked or in-progress has no invoice yet; a cancelled one
never gets one. `WashPackage` gets a linked service Product the spa/
saloon way (`create_wash_package()`) since packages ARE a small, finite,
reusable list (Basic/Premium/Full Detail × vehicle type) — the opposite
shape from textile's per-order pricing. Added `WashOrder.sales_invoice`
(mirroring `TailoringOrder`'s field) since it didn't exist yet.

Found and fixed while writing tests: `complete_wash()` calling
`order.scheduled_at.date()` crashed with `AttributeError` when
`scheduled_at` was still a raw string on the in-memory object (a
`DateTimeField` holds whatever Python value was assigned until the row is
re-fetched from the DB) — added the same `isinstance(..., str)` /
`parse_datetime()` coercion `spa`/`saloon`'s `book_appointment()` already
carries, for the same reason.

## Also fixed: three more webapp (Django-template) call sites

Same class of gap Part 2 found for saloon/beauty_parlour — the
Django-template UI existed independently of the DRF API and needed its
own fixes:

- textile's `order_add` view now passes `user=request.user` and
  `warehouse=_default_warehouse(company)` to `create_tailoring_order()`.
- vehicle_wash's `wash_package_add` view called `form.save()` directly
  (bare model write, bypassing `create_wash_package()`) — every package
  created through the web UI would have had `product=None` forever. Now
  calls `wash_services.create_wash_package()`.
- vehicle_wash's `wash_order_complete` view now passes `user=request.user`
  and `warehouse=_default_warehouse(company)` to `complete_wash()`.

## Verified

```
python manage.py check                    # 0 issues
python manage.py makemigrations --check   # clean
pytest                                     # 149 passed (137 before this phase + 12 new)
```

## The 8-vertical invoice-linkage gap (PHASE24/25's finding) is now fully closed

beauty_parlour, cycle_shop, medical_shop, mobile_shop, protein_shop,
saloon, textile, vehicle_wash — all eight now invoice correctly, each
through the case that actually fits its business model (per-unit
physical goods, per-batch goods, named services, custom-priced jobs, or
bill-on-completion), verified by 149 passing tests across three phases.

## Still open (unrelated to this gap, unchanged from earlier notes)

- CompanyCounter true concurrency test.
- `general_retail` not a separate vertical — open design decision.
- Repo housekeeping: stray root files, the broken brace-literal template
  folder, `phase24-drop-in.zip`.
