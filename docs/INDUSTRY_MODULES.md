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

## Recruitment (recruitment_agency)
Menu: 🧑‍💼 Recruitment. It replaces the generic project menu for this type.
- **Clients:** employers, kept as customers. Add one, then go straight to its job order. The job-order form can also create a new client inline.
- **Job orders (JO-):** position, how many people, location, salary and benefits, preferred nationality and gender, our fee per person, the replacement guarantee period and the needed-by date. A board shows each candidate per stage, with a one-tap move. Matching candidates are suggested, and new ones can be added inline. The job can be shared on WhatsApp, and the client can get a status update.
- **Candidates (CN-):** passport (no duplicates, with expiry), trade, nationality, experience, expected salary, sub-agent (a supplier) and a CV upload (PDF, Word or photo, up to 8 MB, served only to logged-in users). There is an Excel export.
- **Placement:** CV sent → shortlisted → interview (date and time) → selected → medical (an unfit result rejects the placement) → visa (number and expiry) → ticket → joined.
  - Joining sets the guarantee end date. The job is marked filled once every vacancy has joined, and nobody can join beyond the vacancies.
  - The client and the candidate can each be billed once.
  - Costs (medical, visa, ticket, agent commission, documents) are recorded in Expenses under "Recruitment costs". Profit is shown per placement.
  - WhatsApp messages for the interview, selection and travel date are ready to send.
- **Nightly reminders:** passports expiring within 90 days, visas expiring before travel (14 days), today's interviews and guarantees ending in 7 days.
- The generic project form, used by every project-type business, can now create a new client inline.
- **Careers website** (Recruitment → 🌐 Careers website):
  - Each agency gets its own public site at `/careers/<name>/`. It shows their name, logo, colour, headline, about text, services, countries, WhatsApp and licence, with an EN/AR/ML switch.
  - Only open jobs ticked "Show on website" are listed, and the client's name is never shown.
  - Job seekers apply with name, phone, passport, nationality, experience and a CV. The application becomes a candidate in **that agency only**, in the "Applied online" stage of the job, or as a general application. The agency gets a notification.
  - If the same passport or phone applies again, the existing candidate is updated instead of duplicated.
  - Spam protection: a honeypot field, 8 applications per hour per IP, and a check on CV file type and size.
  - For an agency that already has a website: a Careers link, an iframe embed (`?embed=1`), a public JSON job feed (`jobs.json`), and a form or JSON POST from their own domain, allowed through CORS for the addresses they list. Their server can send `X-Api-Key` to skip the rate limit.
  - **Connect an existing career page** (no new website needed): enter the agency's domain under "Connect your existing career page" and paste one line on their career page: `<script src="…/careers/<name>/connect.js" defer></script>`.
    - The script finds the career form and maps its fields automatically: first and last name, mobile, email, passport, position, nationality, experience and the CV file. Fields it doesn't recognise go into the message.
    - It sends a copy of each application here, and the site's own form keeps working, whether it is a normal post or an AJAX/WordPress form.
    - A position matching an open job order (by title) puts the person in that job's "Applied online" stage.
    - Only listed domains are accepted. The hosted BookPilot page can stay switched off.
  - **Detailed recruitment form for any website** (common to every agency): `<div class="bookpilot-form"></div><script src="…/careers/<name>/form.js" defer></script>`, or the downloadable **WordPress plugin** (`[bookpilot_form]` shortcode, with options `job`, `lang` (en/ar), `color` and `thanks`).
    - Fields: job (published jobs or "any"), trade, experience, Gulf experience, expected salary, qualification, languages, driving licence, joining time, name, gender, DOB, nationality, marital status, phone, email, location, passport number and expiry, CV, message, and consent.
    - Profile fields are saved on the candidate. The rest goes into notes.
    - Works from any domain (CORS reflects the caller's origin for widget posts). Honeypot and rate limit apply.
  - Code: `apps/industry/careers.py`, `apps/webapp/careers_views.py`, `templates/webapp/careers/` (`connect.js`, `form.js`, `wp_plugin.php.txt`).

## Staff & HR (every business type)

The **People → Staff & HR / Attendance / Payroll & advances** menu is available to all 108 business types. The views are in `apps/webapp/hr_views.py` and the rules are in `apps/employees/services.py`.

- **Staff:** details, job title, a linked login, and monthly salary (basic, allowances, fixed deductions, overtime rate). Someone with salary history is moved to former staff instead of being deleted.
- **Attendance:** one screen per day (present / absent / half day / leave / holiday, plus check-in/out times) and a month grid.
- **Leave:** requests with approve/reject, balances per leave type, paid and unpaid types, and holidays. Weekly off days come from HR settings (Friday by default in the Gulf, Sunday in India).
- **Salary advances:** paid from cash or bank (Dr 1300 Staff Salary Advances, Cr Cash/Bank) with a monthly instalment.
  - Payroll deducts the instalment automatically, oldest advance first, and never below zero net pay.
  - Staff can also pay back in cash or by bank.
  - Reversing a payroll puts the recovered amounts back on the advance.
- **Payroll:** calculate the month, then approve and pay.
  - Calculate: gross = basic + allowances + approved overtime − unpaid absence. Unpaid absence is (basic + allowances) ÷ days in the month × (absent + ½ half days + approved unpaid leave).
  - Approve: Dr 5200 gross; Cr 2200 net, 2250 deductions, 1300 advances.
  - Pay: Dr 2200, Cr Cash/Bank. Payslips can be printed or sent on WhatsApp.
- **Documents:** QID, passport, visa and similar, sorted by expiry. The existing expiry notifications apply.

## Business back-office (every business type)

These pages put the existing ledger, sales, purchase, stock, bank and CRM services on the web. Each one works on phones and has Malayalam and Arabic.

| Menu | What it does | Code |
|---|---|---|
| Finance → Accounts & reports | P&L, balance sheet, trial balance, cash flow, VAT/tax, chart of accounts, ledgers, manual journal entries (balanced; manual ones can be cancelled) | `accounts_views.py` |
| Finance → Bank & cash | Cash/bank accounts with balances, money in/out, transfers, CSV statement import (no duplicates), suggested matching and reconciliation | `banking_views.py` |
| People → Money to collect | Ageing (0-30/31-60/61-90/90+), customer statements, payments that settle the oldest bills first (extra money is kept as an advance), WhatsApp reminders, follow-up notes, credit limits | `receivables_views.py` |
| Sales → Invoices / Quotations / Sales orders | QT-/SO-/DN- numbered documents. A quote becomes an invoice or an order. Orders can be delivered in parts, each part with a delivery note. Delivered items are invoiced without taking stock out twice. | `sales_docs_views.py` |
| Sales → Leads & pipeline, Price lists & offers | Leads with activities and conversion to customers, a pipeline board, price lists (per customer or general), and offers applied in the POS and on new quotes | `crm_views.py` |
| Purchases → Purchase orders | PO → partial goods receipts (GRN) → supplier bill, a prefill for low-stock items, a bill page with payments and returns (capped at what was bought) | `purchase_docs_views.py` |
| Business → Stock & inventory | Stock per location with value, adjustments (audited), transfers, stock taking, batches with expiry, serial/IMEI lookup, and movement history. Batch items sold without a chosen batch are taken from the batch that expires first. | `stock_views.py` |
| Settings → Tax & currency, Activity log | Tax registration and codes, exchange rates, and the company's own audit trail | `banking_views.py` |

## Automation, online payments and control

| Menu / link | What it does | Code |
|---|---|---|
| Settings → Reminders & alerts | Days-before settings per reminder type (customer/supplier bills due, stock expiry, memberships, the plan, overdue bills, low stock) and whether each one emails. The nightly checks run once a day through `run_daily_jobs`. | `apps/notifications/rules.py`, `daily.py` |
| Finance → Daily report | The day's sales, money received, expenses, profit, dues, low stock and top items. It is emailed each night to owners and any extra addresses, and can be shared on WhatsApp with one tap. | `apps/notifications/daily_report.py` |
| Finance → Budgets | A monthly budget per expense category. A notification is sent once at the warning % and once when the budget is exceeded. | `apps/expenses/budgets.py` |
| Finance → Online payments | The business connects its own SkipCash (Qatar) or Razorpay (India) keys, which are stored encrypted. Shared bills show a **Pay now** button. The payment is confirmed with the gateway before it is applied to the oldest open bills. Bank, IBAN, UPI or Fawran details can be shown instead. | `apps/sales/online_pay.py`, `pay_views.py` |
| Customer portal `/c/<token>/` | A signed link per customer that shows unpaid bills, a statement and recent bills, with a button to pay the whole balance. Copy it from the customer's account page; WhatsApp reminders include it. | `pay_views.py` |
| 📊 Excel buttons | .xlsx downloads for P&L, balance sheet, trial balance, ledgers, stock, invoices, payroll, receivables, customer statements, expenses and budgets. They use a built-in writer with no extra dependency, and text never becomes a formula. | `apps/webapp/xlsx.py` |
| Team → Role & branches | Tick the branches a team member works at. They then sell from those branches only, and see only their stock, bills and restaurant orders; stock transfers go out of their own branch. Owners always see everything. | `apps/inventory/branch_access.py` |

### Nightly jobs on Render
Render has no worker here, so `.github/workflows/daily-jobs.yml` calls `POST /cron/daily/` every night with the `X-Cron-Key` header. Setup:
1. Copy Render's generated `CRON_SECRET` into the GitHub repository secret `CRON_SECRET`.
2. Optionally set the repository variable `BOOKPILOT_URL` (default: the Render URL).
3. Email settings (`EMAIL_HOST` etc.) are needed for the reminder and report emails.
