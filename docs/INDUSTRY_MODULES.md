# Industry modules

All 108 business types share the core (POS, stock, sales, purchases, finance,
people). On top of that, some types get a module built for how they work. The
map lives in `apps/modules/catalog.py` (`INDUSTRY_FEATURES`); a company gets a
module if its main business type, or any extra business suite it has turned on,
is listed. The pages are guarded by `require_industry(...)` in
`apps/webapp/industry_access.py`, and the menu section comes from
`templates/webapp/_industry_nav.html`.

| Module | Business types | Where |
|---|---|---|
| Bookings & calendar | Hotel apartment, car rental, equipment rental, wedding/party hall, co-working space | `/bookings/` |
| Sell by weight + scale barcodes | Supermarket, grocery, fish & meat, fruits & vegetables, bakery, agricultural supplies | `/pos/scale/`, product form, POS |
| Courses, fees & attendance | School/training institute, tuition centre, nursery/daycare, driving school | `/education/` |
| Properties, leases & rent | Property management, real-estate brokerage | `/property/` |
| Gold rates & jewellery prices | Jewellery shop | `/jewellery/gold-rates/` |

The code is in `apps/industry/` (models, services in `bookings.py`,
`education.py`, `property.py`, `gold.py`) with views in `apps/webapp/*_views.py`.
Every module bills through the normal sales invoices, so payments, receipts,
WhatsApp/email sharing, VAT and reports work the same everywhere.

## Bookings

- Resources (rooms, vehicles, halls, desks) with a price per night, day, event or hour.
- The calendar board shows each resource by day. Double bookings and over-capacity are refused.
- A booking records the advance and a refundable security deposit. It moves from reserved → checked in → checked out, or to cancelled or no-show.
- Check-out bills the actual time used; a late return is charged up to the real return time. Extras and a discount can be added. The advance is counted as already paid.

## Sell by weight

- Tick "Sold by weight" on a product: its price is per kg, and the POS asks for the weight (0.001 kg steps).
- Scale labels (EAN-13) can carry the weight or the price. Set the prefixes, the item-code length and the value type once in Weighing scale settings, then give each item a scale code (PLU).

## Education

- Courses (or batches, classes, packages) are billed monthly or as a one-time fee, with an optional seat limit.
- Enrolment has a per-student discount.
- The monthly run creates one invoice per student for all their courses. Running it again never bills twice.
- The fees-due list has WhatsApp/email reminders. Attendance can be taken per day with rates per student.

## Property

- Properties → units (rent, bedrooms). A unit can have only one active lease at a time.
- A lease records the tenant, dates, rent, due day and deposit.
- The monthly rent run creates invoices due on each lease's due day. Running it again never bills twice.
- The home page shows overdue rent and leases ending within 60 days.

## Gold

- Enter the day's rate per gram for 24K/22K/21K/18K. The history is kept.
- On each jewellery product, set the weight, karat, making charge (per gram, fixed, or % of gold value) and the stones value.
- Price = weight × rate + making + stones. The POS always uses the latest rate. Saving rates can also update every item's stored selling price.
