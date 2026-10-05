"""Guides for the tools every business shares (they sit in the common menu groups)."""
from engine import *

VERTICALS = []
ALL = ["Every business type"]

# ------------------------------------------------------------------ SALES DOCUMENTS
VERTICALS.append(dict(
 slug="quotes-orders", name="Quotations, Sales Orders &amp; Delivery", icon="📝", group="Tools for every business",
 tag="Quote → order → deliver → invoice, with stock and WhatsApp sharing", covers=ALL,
 lead="Send a professional quotation, turn it into a sales order when the customer agrees, deliver in one or more trips with a delivery note, and invoice what was delivered — without typing anything twice.",
 chips=["Quotations", "Sales orders", "Delivery notes", "Invoices", "Price lists &amp; offers"],
 menu_title="Sales", menu=["Leads &amp; pipeline", "Price lists &amp; offers", "Invoices", "Quotations", "Sales orders &amp; delivery", "POS", "Returns &amp; Refunds"],
 flow=[("Quotation", "send on WhatsApp"), ("Accepted", "convert"), ("Sales order", "reserve the work"), ("Deliver", "delivery note"), ("Invoice", "money to collect")],
 glance=[("Quotation", "Items, prices, validity date and notes/terms. Print, PDF or WhatsApp."),
         ("Convert", "One button turns a quotation into a sales order or straight into an invoice."),
         ("Partial delivery", "Deliver some now and the rest later; each trip gets its own delivery note."),
         ("Price lists &amp; offers", "Special prices for a customer or a period are filled in automatically.")],
 setup=[("Check your products and customers", ["Products and customers must exist first — but you can also type a <b>New customer name</b> right on the quotation."])],
 tasks=[
  ("Write a quotation", ["[[[Sales]]] → [[Quotations]] → [[New quotation]]. Choose the customer, [[Add item]] for each line, set <b>Valid until</b> and <b>Notes / terms</b>. Save.",
                         "Press [[Send on WhatsApp]] or [[Print / PDF]], then [[Mark as sent]]."]),
  ("Customer said yes", ["Open the quotation → [[Customer accepted]] → [[Convert to sales order]] (or [[Convert to invoice]] for a simple job)."]),
  ("Deliver and invoice", ["Open the sales order → [[Deliver now]]. Enter the quantity for this trip.",
                           "Choose [[Deliver &amp; invoice]] to bill at once, or [[Deliver only]] and later [[Invoice delivered items]].",
                           "Print the <b>Delivery note</b> for the driver; the customer signs <i>Received by</i>."],
   dict(note="Stock goes down when goods are delivered, not when the order is taken.")),
  ("Set special prices", ["[[Price lists &amp; offers]] → [[Create price list]] for a customer, or [[Save offer]] for a period (e.g. Ramadan 10%). The POS and new quotations use them automatically."]),
  ("Track leads", ["[[Leads &amp; pipeline]] → [[New lead]]. Move it through the pipeline, add follow-ups, and when they buy press [[Convert to customer]]."]),
 ],
 auto=["Converting never re-types items or prices.", "Expired quotations are marked <b>Expired</b>.", "Invoices post to your accounts and appear in Money to collect."],
 reports=[("Quotations", "Sent, accepted, rejected, expired"), ("Sales orders", "Ordered vs delivered vs invoiced"), ("Sales pipeline", "Open deals value and expected sales")],
 statuses=[("Sent", "info", "Waiting for the customer"), ("Accepted", "ok", "Ready to convert"), ("Delivered", "ok", "Goods handed over"),
           ("Invoiced", "ok", "Billed"), ("Expired", "warn", "Validity date passed"), ("Cancelled", "bad", "Cancelled")],
 faq=[("Can I change a quotation after sending?", "Yes, while it is not converted. Send it again after editing.")],
))

# ------------------------------------------------------------------ PURCHASES
VERTICALS.append(dict(
 slug="purchases-suppliers", name="Purchase Orders, Receiving &amp; Suppliers", icon="📦", group="Tools for every business",
 tag="Order from suppliers, receive goods, record bills, pay and return", covers=ALL,
 lead="Send purchase orders, receive goods (all at once or in parts), record the supplier's bill, pay it and return damaged items — stock and what you owe are always right.",
 chips=["Purchase orders", "Goods receipt", "Supplier bills", "Payments", "Returns"],
 menu_title="Purchases", menu=["Purchase orders", "Purchases", "Suppliers", "Purchase Reports"],
 flow=[("Purchase order", "send to supplier"), ("Receive", "goods receipt"), ("Bill", "supplier's bill no."), ("Pay", "cash or bank"), ("Return", "if needed")],
 glance=[("Low stock", "[[Order low-stock items]] fills a purchase order with everything below its reorder level."),
         ("Receive in parts", "Each delivery creates a <b>Goods receipt note</b>."),
         ("What you owe", "Each supplier shows bills, payments and <b>Still to pay</b>.")],
 setup=[("Add your suppliers", ["[[[Purchases]]] → [[Suppliers]] → add name, phone and opening balance."])],
 tasks=[
  ("Order from a supplier", ["[[Purchase orders]] → [[New purchase order]] (or [[Order low-stock items]]). Add items and quantities, then [[Send to supplier]] on WhatsApp."]),
  ("Receive the goods", ["Open the order → [[Receive now]]. Enter what arrived. Choose [[Receive &amp; record bill]] or [[Receive only]] and later [[Record bill for received items]]."]),
  ("Pay the supplier", ["Open the supplier or the bill → [[Pay supplier]]: amount, date, cash or bank."]),
  ("Return items", ["Open the bill → [[Return items to supplier]] → enter <b>Return qty</b> and reason → [[Save return]]. Stock goes down and the supplier owes you."]),
 ],
 auto=["Stock goes up when goods are received.", "Supplier bills due soon appear in Reminders.", "Payments post to Bank &amp; cash."],
 reports=[("Purchase Reports", "Purchased, paid, outstanding, by supplier"), ("Supplier bills", "Unpaid bills with due dates")],
 statuses=[("Ordered", "info", "Sent to supplier"), ("Received", "ok", "Goods arrived"), ("Billed", "ok", "Bill recorded"), ("Cancelled", "bad", "Order cancelled")],
 faq=[("Can I record a purchase without a purchase order?", "Yes — [[Purchases]] → [[+ New purchase]] still works for quick buys.")],
))

# ------------------------------------------------------------------ STOCK
VERTICALS.append(dict(
 slug="stock", name="Stock &amp; Inventory", icon="🏷️", group="Tools for every business",
 tag="Adjustments, stock counts, batches &amp; expiry, serial numbers and transfers", covers=ALL,
 lead="Know exactly what is on the shelf: correct stock, count it, track batches and expiry dates, serial/IMEI numbers, and move stock between branches.",
 chips=["Stock counts", "Batches &amp; expiry", "Serial / IMEI", "Transfers", "Stock history"],
 menu_title="Business", menu=["Stock &amp; inventory", "Analytics", "Branches"],
 flow=[("Check", "running low / out"), ("Order", "low-stock PO"), ("Count", "stock taking"), ("Move", "between branches")],
 glance=[("Overview", "Stock value, running low, out of stock and batches expiring in 30 days."),
         ("Stock count", "Count the shelf; the system corrects stock and records the difference."),
         ("Batches", "Sales take stock from the batch that expires first."),
         ("History", "Every movement in and out, with who and why.")],
 setup=[("Set reorder levels", ["On each product set <b>Reorder at</b>. Items at or below it show as <b>Running low</b>."])],
 tasks=[
  ("Correct stock (damage, loss, own use)", ["[[Stock &amp; inventory]] → [[Adjust stock]]. Choose the item, location, <b>Add to stock</b> or <b>Remove from stock</b> and the reason."]),
  ("Do a stock count", ["[[Start stock taking]] → [[Start counting]] (optionally one category). Scan or type each item's counted quantity; leave uncounted items empty.",
                        "[[Save progress]] any time. When done press [[Finish &amp; correct stock]]."]),
  ("Receive a batch with expiry", ["[[Batches &amp; expiry]] → [[Receive a batch]]: item, batch/lot number, expiry date, quantity. Expired stock can be [[Write off]]."]),
  ("Add serial / IMEI numbers", ["[[Serial numbers]] → [[Add serial numbers to stock]] — one per line, or scan one after another."]),
  ("Move stock between branches", ["[[Transfer stock]] → choose From and To, items and quantities → [[Move stock]]."]),
 ],
 auto=["Every sale, purchase, return and transfer updates stock.", "Low-stock and expiry reminders are created every day."],
 reports=[("Stock value (cost)", "What your stock is worth"), ("Stock history", "Every movement"), ("Differences", "Shortage and extra value from counts")],
 statuses=[("In stock", "ok", ""), ("Running low", "warn", "At or below reorder level"), ("Out of stock", "bad", ""), ("Expired", "bad", "Past expiry date")],
 faq=[("Do I need branches for transfers?", "Yes — add a branch or store under Business → Branches first.")],
))

# ------------------------------------------------------------------ CUSTOMERS & MONEY
VERTICALS.append(dict(
 slug="customers-money", name="Customers, Money to Collect &amp; Online Payment", icon="💰", group="Tools for every business",
 tag="Who owes you, statements, reminders, credit limits and pay-now links", covers=ALL,
 lead="See who owes you and how old each bill is, take payments against bills, send statements and WhatsApp reminders, set credit limits and let customers pay online with a link.",
 chips=["Money to collect", "Statements", "Reminders", "Credit limits", "Pay-now link"],
 menu_title="People", menu=["Customers", "Money to collect", "Team", "Staff &amp; HR"],
 flow=[("Sell on credit", "invoice"), ("Remind", "WhatsApp"), ("Receive payment", "apply to bills"), ("Statement", "print / share")],
 glance=[("Overdue by age", "0–30, 31–60, 61–90 and 90+ days."), ("Apply payments", "One payment can clear several bills; extra stays as advance."),
         ("Customer portal", "A private link where the customer sees their bills and pays."), ("Credit limit", "Warns before selling to someone over their limit.")],
 setup=[("Switch on online payment (optional)", ["[[[Finance]]] → [[Online payments]] — connect your payment gateway so invoices get a <b>Pay now</b> button."])],
 tasks=[
  ("Receive a payment", ["[[[People]]] → [[Money to collect]] → the customer → [[Receive payment]]. Enter the amount; it is applied to the oldest bills first. [[Save payment]]."]),
  ("Send a reminder", ["On the customer press [[Send reminder]] — a polite WhatsApp message with the amount due and pay link."]),
  ("Print a statement", ["Open the customer → [[Statement]] → [[Print statement]], or [[Copy customer portal link]]."]),
  ("Set a credit limit", ["Customer → [[Credit settings]]: <b>Credit limit</b> (0 = no limit) and <b>Days to pay</b>."]),
 ],
 auto=["Overdue bills appear in Reminders every morning.", "Online payments mark the invoice paid by themselves."],
 reports=[("Customers owe you", "Total and by customer"), ("Received this month", "Money collected"), ("Follow-ups due", "Promises to chase")],
 statuses=[("Not yet due", "info", ""), ("Overdue", "bad", "Past the due date"), ("In credit", "ok", "Customer paid in advance")],
 faq=[("Can a customer pay part of a bill?", "Yes. The rest stays open.")],
))

# ------------------------------------------------------------------ FINANCE
VERTICALS.append(dict(
 slug="finance", name="Accounts, Bank, Expenses &amp; Reports", icon="📊", group="Tools for every business",
 tag="Bank &amp; cash, accounts reports, cheques, recurring invoices, assets, budgets and the daily report", covers=ALL,
 lead="Every sale, purchase and expense is booked into your accounts automatically. Reconcile the bank, manage post-dated cheques, repeat invoices, depreciate assets, set budgets and get a daily report by email or WhatsApp.",
 chips=["Bank &amp; cash", "Profit &amp; loss", "Balance sheet", "Cheques (PDC)", "Budgets", "Daily report"],
 menu_title="Finance", menu=["Bank &amp; cash", "Daily report", "Accounts &amp; reports", "Cheques (PDC)", "Recurring invoices", "Fixed assets", "Expenses", "Budgets", "Online payments", "Billing"],
 flow=[("Record", "sales, bills, expenses"), ("Reconcile", "bank statement"), ("Review", "profit &amp; loss"), ("Plan", "budgets")],
 glance=[("Accounts &amp; reports", "Profit &amp; loss, balance sheet, trial balance and the full ledger."),
         ("Bank &amp; cash", "All accounts, transfers, and statement import to reconcile."),
         ("Cheques (PDC)", "Cheques to receive and to pay, due this week, deposited, cleared or bounced."),
         ("Recurring invoices", "Bill the same items every month automatically."),
         ("Fixed assets", "Straight-line depreciation posted with one button."),
         ("Daily report", "Sales, profit, cash and overdue money — emailed every night.")],
 setup=[("Add bank and cash accounts", ["[[[Finance]]] → [[Bank &amp; cash]] → [[Add account]] with the opening balance."]),
        ("Tax &amp; currency", ["[[[Settings]]] → [[Tax &amp; currency]]: tax registration number, tax codes and exchange rates."])],
 tasks=[
  ("Record an expense", ["[[Expenses]] → [[+ Add expense]]: category, amount, date, paid from cash or bank."]),
  ("Reconcile the bank", ["[[Bank &amp; cash]] → [[Import bank statement]] (CSV from your bank) → [[Match]] each line, or [[Record &amp; match]] what is missing."]),
  ("Manage a post-dated cheque", ["[[Cheques (PDC)]] → [[Add a cheque]]. Mark it Deposited, Cleared ✓ or Bounced when it happens."]),
  ("Set up a recurring invoice", ["[[Recurring invoices]] → [[New schedule]]: customer, items, repeat (monthly…), first date. It is created automatically every day it is due."]),
  ("Depreciate assets", ["[[Fixed assets]] → [[Add asset]], then each month [[Post depreciation]]. Use [[Sell / scrap]] when it leaves."]),
  ("Set budgets", ["[[Budgets]] → a monthly budget per expense category and a <b>Warn at %</b>. You are alerted when spending crosses it."]),
  ("Get the daily report", ["[[Daily report]] → tick <b>Email me this report every night</b>, add more emails, or [[Send on WhatsApp]]."]),
 ],
 auto=["Double-entry bookkeeping happens in the background.", "Recurring invoices and depreciation run on schedule.", "Over-budget and cheque-due reminders appear in Notifications."],
 reports=[("Profit &amp; loss", "Income minus costs for any period"), ("Balance sheet", "What you own and owe"), ("Trial balance", "For your accountant"),
          ("Excel export", "Most lists have an Excel button")],
 statuses=[("Deposited", "info", "Cheque given to bank"), ("Cleared ✓", "ok", "Money received"), ("Bounced", "bad", "Cheque returned")],
 faq=[("Do I need an accountant?", "Not for daily work. Give your accountant the Accountant role to review reports.")],
))

# ------------------------------------------------------------------ STAFF & HR
VERTICALS.append(dict(
 slug="staff-hr", name="Staff, Attendance &amp; Payroll", icon="👷", group="Tools for every business",
 tag="Staff files, attendance, leave, salary advances and monthly payroll", covers=ALL,
 lead="Keep every employee's details and documents, mark attendance, approve leave, give salary advances and run the monthly payroll — payslips, payments and accounts included.",
 chips=["Staff &amp; documents", "Attendance", "Leave &amp; holidays", "Advances", "Payroll &amp; payslips"],
 menu_title="People", menu=["Customers", "Money to collect", "Team", "Staff &amp; HR", "Attendance", "Payroll &amp; advances"],
 flow=[("Add staff", "salary + documents"), ("Attendance", "daily"), ("Leave", "approve"), ("Payroll", "calculate → approve → pay")],
 glance=[("Documents", "Visa, ID, passport with expiry alerts (30 days)."), ("Attendance", "Present, absent, half day, leave, holiday; [[Mark all present]]."),
         ("Advances", "Given now, recovered from salary each month."), ("Payroll", "Basic + allowances + overtime − absence − advance recovery.")],
 setup=[("Add your staff", ["[[[People]]] → [[Staff &amp; HR]] → [[Add staff]]: name, job title, basic salary, allowances and (optional) app login."]),
        ("HR settings", ["[[HR settings]]: overtime rate, leave types and holidays."])],
 tasks=[
  ("Mark attendance", ["[[Attendance]] → choose the day → mark each person, or [[Mark all present]]. Save."]),
  ("Approve leave", ["[[Leave &amp; holidays]] → [[Add leave]] or approve requests in <b>Leave to approve</b>."]),
  ("Give a salary advance", ["[[Payroll &amp; advances]] → [[Give advance]]: amount and monthly deduction."]),
  ("Run payroll", ["[[Run payroll]] → [[Calculate payroll]] → check the draft → [[Approve payroll]] → [[Pay all]] (cash or bank). Print payslips."]),
 ],
 auto=["Absence and advance recovery are deducted automatically.", "Expiring documents appear in reminders.", "Salaries post to your accounts."],
 reports=[("Monthly salaries", "Gross, deductions and net"), ("Advances to recover", "Balance per person"), ("Monthly attendance", "Present / absent per day")],
 statuses=[("Draft", "warn", "Payroll calculated — check and approve"), ("Approved", "info", "Ready to pay"), ("Paid", "ok", "Salaries paid"), ("Reversed", "bad", "Payroll undone")],
 faq=[("Do staff need a login?", "No. Only people who use the app need a login (People → Team).")],
))

# ------------------------------------------------------------------ WEBSITE
VERTICALS.append(dict(
 slug="website-online", name="Your Website, Online Booking &amp; Orders", icon="🌐", group="Tools for every business",
 tag="A ready website, online booking, a website cart and the WordPress plugin", covers=ALL,
 lead="Get a website that updates itself from BookPilot — menu, products, offers, phone and opening hours. Take booking requests and food orders online, in your customers' language. Already have a WordPress site (for example on Hostinger)? Connect it with the plugin.",
 chips=["My website", "12 languages", "Online booking", "Website cart", "WordPress plugin"],
 menu_title="Your business", menu=["My website", "Online booking", "Online orders"],
 flow=[("Design", "colours, logo, sections"), ("Publish", "your web address"), ("Customers", "book / order"), ("You", "confirm in the app")],
 glance=[("Always up to date", "Change a price in BookPilot and the website changes too."),
         ("Languages", "Pick the main language and the extra languages visitors can switch to."),
         ("Online booking", "Requests arrive in the app; confirm or decline and reply on WhatsApp."),
         ("Website cart", "Restaurants can take pickup and delivery orders (switch it on in Online orders)."),
         ("WordPress", "The BookPilot plugin shows your live menu, cart and forms on any WordPress site.")],
 setup=[
  ("Design and publish your website", ["Open [[My website]]: choose colours, font, logo, cover photo, title and the sections to show.",
                                        "Choose the <b>Website language</b> and tick <b>Visitors can also switch to</b> for more languages. [[Save website]]."],
   dict(note="The Website add-on is switched on by the BookPilot team. Ask us if you see <i>Website add-on is off</i>.")),
  ("Use your existing WordPress site", ["Download the BookPilot plugin from [[[Online booking]]] → [[Website form &amp; WordPress]] (or ask us), upload it in WordPress → Plugins → Add new → Upload, and paste your connection code.",
                                         "Choose the plugin language, then add the shortcodes for menu, cart, booking or careers to your pages."]),
 ],
 tasks=[
  ("Confirm a booking request", ["[[[Online booking]]] → [[Booking requests]] → [[Confirm booking]] or [[Decline]], then [[Tell the customer]]."]),
  ("Accept a website order", ["[[🛒 Online orders]] → [[Accept &amp; send to kitchen]] or [[Reject]]."]),
  ("Pause online orders", ["In Online orders press [[Pause orders]] when the kitchen is busy. The menu stays visible."]),
 ],
 auto=["Menu, prices, offers and contact details are always live.", "The cart shows only items you sell online and checks prices on the server.",
       "Customers get a tracking page for their order."],
 reports=[("Online orders", "New, accepted, rejected"), ("Booking requests", "Received, confirmed, declined")], statuses=[],
 faq=[("Do menu item names get translated?", "No — they stay as you typed them. Buttons, headings and the cart are translated."),
      ("Can I use my own domain?", "Yes. Ask us to connect it to your BookPilot website.")],
))

# ------------------------------------------------------------------ DEVICES, OFFLINE, APPS
VERTICALS.append(dict(
 slug="devices-apps", name="Printers, Devices, Offline &amp; Apps", icon="🖨️", group="Tools for every business",
 tag="Receipt and kitchen printers, cash drawer, scanner, customer display, offline POS and the apps", covers=ALL,
 lead="Connect receipt and kitchen printers, cash drawer, barcode scanner and a customer display. Keep billing when the internet stops. Install BookPilot on Windows, Mac, Android or iPhone.",
 chips=["Printers", "Cash drawer", "Scanner", "Offline POS", "Desktop &amp; mobile apps"],
 menu_title="Settings", menu=["Reminders &amp; alerts", "Tax &amp; currency", "Activity log", "Notifications", "Settings", "Devices &amp; Printers", "Security &amp; 2FA", "Backups"],
 flow=[("Connect devices", "once"), ("Test print", ""), ("Sell", "online or offline"), ("Sync", "automatic")],
 glance=[("Printers", "Receipt printer for bills and a kitchen printer for KOT."), ("Cash drawer", "Opens on cash payments."),
         ("Offline POS", "Saves bills on the device and syncs later."), ("Apps", "[[Install app]] on the website, or the desktop and mobile apps.")],
 setup=[("Connect your devices", ["[[[Settings]]] → [[Devices &amp; Printers]]. Choose each device and press the test button."])],
 tasks=[("Bill without internet", ["Open [[Offline POS]] (restaurant) or the POS; keep billing. When the connection is back press [[Sync now]] or wait — it syncs by itself."]),
        ("Install the app", ["On the BookPilot website press [[⬇ Install app]], or install the desktop / Android / iPhone app we send you."])],
 auto=["Offline bills sync automatically and get their invoice numbers.", "The last menu and prices are kept on the device."],
 reports=[("Bills on this device", "Offline bills waiting to sync")], statuses=[],
 faq=[("Will I lose bills if the internet stops?", "No. Offline bills stay on the device until they sync. Do not clear the browser data on that device before syncing.")],
))

# ------------------------------------------------------------------ SECURITY & SETTINGS
VERTICALS.append(dict(
 slug="security-settings", name="Languages, Security, Backups &amp; Settings", icon="🔐", group="Tools for every business",
 tag="12 languages, two-step login, backups, team roles, branches, reminders and activity log", covers=ALL,
 lead="Use BookPilot in your language, protect your account with two-step login, keep automatic daily backups (with a copy in Google Drive), control what each person can do and see every change in the activity log.",
 chips=["12 languages", "Two-step login", "Daily backups", "Roles &amp; branches", "Activity log"],
 menu_title="Settings", menu=["Reminders &amp; alerts", "Tax &amp; currency", "Activity log", "Notifications", "Settings", "Devices &amp; Printers", "Security &amp; 2FA", "Backups"],
 flow=[("Language", "top-right 🌐"), ("2-step login", "owners &amp; admins"), ("Backups", "daily + Drive"), ("Roles", "per person")],
 glance=[("Languages", "English, العربية, മലയാളം, हिन्दी, اردو, தமிழ், বাংলা, नेपाली, Filipino, Français, Español, Türkçe, 中文."),
         ("Two-step login", "A 6-digit code from your phone after the password, with recovery codes."),
         ("Backups", "Automatic every day; download any time; optional Google Drive copy."),
         ("Branch access", "Limit a staff member to their own branch.")],
 setup=[
  ("Choose your language", ["Press the 🌐 button at the top-right and pick your language. Each person can choose their own."]),
  ("Switch on two-step login", ["[[[Settings]]] → [[Security &amp; 2FA]] → install Google Authenticator, Microsoft Authenticator or Authy → scan the QR code → type the 6-digit code.",
                                "Save the recovery codes somewhere safe."],
   dict(warn="Strongly recommended for owners and admins.")),
  ("Check your backups", ["[[Backups]]: automatic daily backup is on. Press [[Back up now]] any time, or [[Connect Google Drive]] for an extra copy."]),
 ],
 tasks=[
  ("Give someone a login", ["[[[People]]] → [[Team]] → add a person, pick a role and (optional) the branches they work at."]),
  ("See who changed what", ["[[Activity log]] lists every important change with the user and time."]),
  ("Choose reminders", ["[[Reminders &amp; alerts]]: customer bills due, supplier bills due, stock expiring, memberships ending, low stock — and how many days before."]),
  ("Download all your data", ["[[Settings]] → <b>Backup &amp; export</b> → [[Download all my data]] (zip)."]),
 ],
 auto=["A backup is made every night.", "Reminders are checked every morning.", "Sign-in is locked for a while after many wrong passwords."],
 reports=[("Activity log", "Who did what and when"), ("Backups", "Last backup and files kept")], statuses=[],
 faq=[("I lost my phone with the authenticator.", "Sign in with one of your recovery codes, then set up two-step login again."),
      ("Does changing language change my data?", "No. Only the screens change; your products and customers stay as typed.")],
))
