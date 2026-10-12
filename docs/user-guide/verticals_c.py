from engine import *
from verticals_a import gs, GS, appt_business
VERTICALS = []

RETAIL_COVERS = ["Watch Shop","Perfume Shop","Book &amp; Stationery Shop","Retail Shop","Supermarket","Grocery Store","Clothing Store","Electronics Store","Computer Shop","Furniture Store","Hardware Store","Cosmetics Store","Jewelry Shop","Auto Spare Parts","Medical Equipment Store","Flower Shop","Pet Shop","Bakery","Trading Company","Wholesale Business","Import &amp; Export","Car Showroom","Printing Shop","Manufacturing","Industrial Services","General Retail","Ladies Fashion / Boutique","Footwear / Shoe Shop","Kids / Baby Products Store","Toys &amp; Gift Shop","Home Appliances Store","Electrical &amp; Plumbing Store","Building Materials Store","Tyre &amp; Battery Shop","E-commerce / Online Store","Mobile Accessories Shop","Uniform Shop","Kitchenware / Household Store","Musical Instruments Shop","Optical Shop","Fuel Station","Agricultural Supplies Store"]

VERTICALS.append(dict(
 slug="retail-shop", name="Retail, Trading &amp; Wholesale", icon="🛍️", group="Retail & product shops",
 tag="Any shop that sells products — with stock, POS and sales list",
 covers=RETAIL_COVERS,
 lead="The complete toolkit for shops and trading businesses: products with stock, fast POS billing, sales records with PDF invoices, purchases from suppliers and reports.",
 chips=["Products &amp; stock","POS","Sales &amp; PDF invoices","Barcodes"],
 menu_title="Your business name", menu=["Categories","Products","Units","Brands","Print Barcodes","Sales","Reports"],
 flow=[("Units, brands, categories","one time"),("Add products","or import CSV"),("Buy stock","Purchases"),("Sell","POS or Sales"),("Reports","daily")],
 glance=[("Products","SKU, category, brand, unit, cost price, selling price and reorder level."),
         ("Two ways to sell","Fast counter billing on the POS, or <b>Sales → + New sale</b> for named customers."),
         ("PDF invoices","Print or share an invoice for any sale."),
         ("Reports","Revenue, number of invoices and top-selling products.")],
 setup=[
  ("Add units, brands and categories",
   ["Open [[Units]] → add what you sell in: <b>pcs, kg, box, meter, litre</b>.",
    "Open [[Brands]] and [[Categories]] and add the ones you deal in. You can add more any time."]),
  ("Add your products",
   ["Open [[Products]] → [[+ Add product]] and fill <b>SKU</b>, <b>Name</b>, <b>Category</b>, <b>Brand</b>, <b>Unit</b>, <b>Cost price</b>, <b>Selling price</b> and <b>Reorder level</b>.",
    "Use <b>Extra details</b> (one per line, like <code>Material: Cotton</code>) for anything else worth recording."],
   dict(tip="Have hundreds of items? Use [[Import CSV]] on the Products page. Required columns: <b>SKU, Name, Unit, Selling Price</b>.")),
  ("Bring in your opening stock",
   ["Open [[[Purchases]]] → [[Purchases]] → [[+ New purchase]] for each supplier delivery to add stock. See Suppliers &amp; purchases in Getting started."]),
 ],
 tasks=[
  ("Bill customers at the counter (POS)",
   ["Open [[[Sales]]] → [[POS]]. Search by name or SKU and click to add.",
    "Choose the customer (or leave <b>Walk-in Customer</b>), a coupon if any and <b>Cash / Card / Bank Transfer</b>.",
    "Press [[Complete Sale]] and then <b>Print receipt</b>."],
   dict(tip=f"Details: {gs('pos','Getting started → POS')}.")),
  ("Record a sale for a named customer",
   ["Open [[Sales]] (under your business menu) → [[+ New sale]].",
    "Choose the <b>Customer</b> and <b>Product</b>, enter <b>Quantity</b>, confirm <b>Unit price</b> (it defaults to the selling price) and set the <b>Date</b>.",
    "Save. You will see <i>“Sale recorded.”</i>"]),
  ("Print or send an invoice",
   ["Open [[Sales]] and press [[PDF]] on the invoice row. Print it or save it and send it on WhatsApp or email."]),
  ("Export your sales",
   ["On [[Sales]] press [[Export CSV]] to download the list for Excel."]),
  ("Print barcode labels",
   ["Open [[Print Barcodes]], select products and label counts, then [[Generate labels]]."]),
  ("Handle returns",
   ["Open [[Returns &amp; Refunds]] → [[+ New return]] and enter the invoice number. See Getting started → Returns."]),
  ("Check performance",
   ["Open [[Reports]] for Revenue, number of Invoices and Top-selling products.",
    "Open [[Analytics]] for sales by day, payment methods, expenses and net profit."]),
 ],
 auto=["Every sale creates an invoice, reduces stock and posts to your books.",
       "Every purchase increases stock and records what you owe suppliers.",
       "Low-stock and overdue-invoice notifications are created for you every day."],
 reports=[("Revenue","Total sales value"),("Invoices","Number of invoices raised"),("Top-selling products","Best sellers by units and revenue"),("Analytics","Sales, expenses, profit and payment mix")],
 statuses=[],
 faq=[("My business is not named exactly like this.","If you sell products, this guide is yours. Your menu shows a section with your business name — it holds Categories, Products, Sales and Reports."),
      ("Can I keep separate stock for two shops?","Yes — add each shop under Branches and pick the branch in POS and Purchases.")],
))

SERVICE_COVERS = ["Dental Clinic","Medical Clinic","Physiotherapy Center","Veterinary Clinic","Photography / Videography Studio","Consultancy","Auto Garage","Repair Services","Home Services","Laundry / Dry Cleaning","Diagnostic Laboratory","Law Firm / Legal Consultancy","Insurance Brokerage","Pest Control Company","Moving / Packing Company","AC Maintenance Company","Electronics Repair Centre","Computer / Laptop Repair","Home Nursing","Cleaning Equipment Service","Immigration / Document Clearing","Travel Agency"]
svc = appt_business("service-appointments","Clinics, Studios &amp; Appointment Services","🗓️","Beauty, salon & spa","Appointments, services and staff for clinics, garages, studios and schools",SERVICE_COVERS,
   "Stylist","Doctors, technicians &amp; staff",None,
   "Book clients or patients, assign staff, track completed work and see revenue by service — ideal for clinics, garages, studios, schools and home-service businesses.",
   menu_title="Your business name", examples="Consultation, Teeth cleaning, Oil change, Portrait session, Driving lesson",
   form_note="On the booking form the staff field is labelled <b>Stylist</b> and the commission field <b>Stylist commission %</b>. Simply choose your doctor, technician, trainer or photographer there.",
   staff_role="Doctor / Technician / Instructor",
   extra_faq=[("Why does the form say “Stylist”?","The same booking screen is shared with salons. Choose whoever performs the service — the label does not change how it works.")])
svc["chips"] = ["Job cards", "Appointments calendar", "Parts &amp; labour bill", "Staff phone page"] + svc["chips"][:2]
svc["menu"] = ["🧰 Job cards", "📅 Appointments calendar"] + svc["menu"]
svc["tasks"] = [
 ("Open a job card (walk-in or appointment)",
  ["Open [[🧰 Job cards]] → [[+ New job / appointment]]. Choose the customer or type a new name and WhatsApp number.",
   "Fill <b>what it is about</b> (patient, car with plate, laptop with serial…) and the <b>job / complaint</b>.",
   "Choose the <b>staff</b>. For an appointment pick the date and time; leave it empty for a walk-in. Add <b>Ready by</b> if you promised a time.",
   "If that staff member is already busy at that time you are warned first — press Save again to book anyway."],
  dict(tip="Online booking requests become job cards by themselves when you confirm them.")),
 ("Add parts and work, then bill",
  ["On the job card add each <b>part</b> from stock (its price fills in) or type the <b>labour / service</b> with a price.",
   "Move the job along: [[Start work]] → [[Waiting (parts / approval)]] → [[Ready for the customer]]. Late jobs turn red.",
   "Press [[WhatsApp status]] to send the customer the update with their status link.",
   "When the customer pays press [[Make bill &amp; close job]] (cash, card, bank or pay later). Parts come out of stock and one bill is made."],
  dict(note="Warranty or package work? Use [[Close without a bill]].")),
 ("Plan the day on the calendar",
  ["Open [[📅 Appointments calendar]]: one column per staff member with their appointments for the day.",
   "Tap a free time under a name to book straight into that slot. Use ← → to change the day."]),
 ("Give each staff member their phone page",
  ["At the bottom of the calendar press [[Make link]] for a staff member, then [[Send link]] to WhatsApp it.",
   "On their phone they see only their jobs and press [[Start work]], [[Waiting]] or [[Ready]], and can add notes. No login and no prices.",
   "Phone lost? Press [[New link]] — the old link stops working."]),
] + svc["tasks"]
VERTICALS.append(svc)

AGENCY_COVERS = ["Advertising Agency","Digital Marketing Agency","Web Development","IT Services","Software Company","Accounting / Audit","Security Services","Event Management","Cleaning Company","Maintenance Company","Landscaping Company","Logistics / Transport Company","Courier / Delivery Company","Interior Design Company","Facility Management"]
VERTICALS.append(dict(
 slug="project-agency", name="Agencies &amp; Project-based Businesses", icon="📁", group="Projects & agencies",
 tag="Projects, vendors/freelancers, project costs and profit",
 covers=AGENCY_COVERS,
 lead="Run every job as a project with a budget and fee, record what you spend on it, and know your profit — perfect for agencies, IT companies, event managers, cleaning and maintenance firms.",
 chips=["Projects","Vendors &amp; freelancers","Cost tracking","Project profit"],
 menu_title="Your business name", menu=["Projects","Contractors","Reports"],
 flow=[("Add vendors","freelancers, subcontractors"),("Create project","budget + fee"),("Record costs","per project"),("Open project","budget vs spent"),("Reports","by status")],
 glance=[("Projects","Client, dates, budget (planned cost) and contract value (your fee)."),
         ("Contractors","Your freelancers, subcontractors and vendors."),
         ("Project costs","Material, Labour, Contractor, Equipment or Other."),
         ("Profit","Budget, spent, remaining and profit on each project.")],
 setup=[
  ("Add your freelancers / vendors",
   ["Open your business section → [[Contractors]] → [[+ Add contractor]].",
    "Enter <b>Name</b>, <b>Phone</b> and <b>Specialty</b> (e.g. <i>Graphic designer</i>, <i>Security guard supplier</i>)."],
   dict(note="The screen says <b>Contractors</b> — use it for any outside person or company you pay for project work.")),
  ("Add clients as customers",
   ["Open [[[People]]] → [[Customers]] → [[+ Add customer]] for each client so you can attach them to projects."]),
 ],
 tasks=[
  ("Create a project",
   ["Open [[Projects]] → [[+ New project]].",
    "Enter the project <b>Name</b>, choose the <b>Client</b> and add the <b>Site address</b> (or location).",
    "Set <b>Start date</b>, <b>End date</b>, <b>Budget</b> (planned cost) and <b>Contract value</b> (fee you charge).",
    "Set <b>Status</b> (Planning, Active, On Hold, Completed, Cancelled) and save."]),
  ("Record a cost on a project",
   ["Open the project ([[View]]) → [[+ Record expense]].",
    "Choose the <b>Category</b> — use <b>Contractor</b> for freelancers/vendors, <b>Labour</b> for staff time, <b>Material</b> for purchases, <b>Equipment</b> for tools/rentals, <b>Other</b> for the rest.",
    "Choose the <b>Contractor</b> (optional), <b>Amount</b>, <b>Date</b>, <b>Description</b>, and <b>Cash / Bank</b>. Save."]),
  ("Check profit on a project",
   ["Open the project: <b>Budget</b>, <b>Spent</b>, <b>Budget remaining</b> and <b>Project profit</b> update with every cost you record."]),
  ("Track everyday overheads (rent, salaries, software)",
   ["Use [[[Finance]]] → [[Expenses]] → [[+ Add expense]]. See Getting started → Expenses."]),
  ("See the big picture",
   ["Open [[Reports]] for the number of projects in Planning / Active / Completed and total contract value."]),
 ],
 auto=["Every project cost is posted to your accounting books.",
       "Profit per project is calculated for you.",
       "Your Overview shows active and total projects."],
 reports=[("Planning","Projects not yet started"),("Active","Projects in progress"),("Completed","Finished projects"),("Total contract value","Total fees across all projects")],
 statuses=[("Planning","grey","Not started"),("Active","ok","In progress"),("On Hold","warn","Paused"),("Completed","info","Finished"),("Cancelled","bad","Stopped")],
 faq=[("What should I use “Contractors” for?","Any outside person or supplier of services on a project — freelancers, subcontractors, vendors."),
      ("Can I invoice my client?","Yes, through the Sales section. Ask us if you want a set-up for milestone/stage invoices.")],
))

# Maintenance / service contracts (AMC) — service businesses and field-service companies
AMC_TASK = ("Run maintenance contracts (AMC)",
  ["Open [[📑 Service contracts (AMC)]] → [[+ New contract]]. Choose the customer, give it a name (e.g. <i>AC maintenance – 4 units</i>), the site and the start and end dates.",
   "Choose how often to visit (every month, 3 months, 6 months…), the usual time, staff and what to do on every visit.",
   "Enter the contract value and how to bill: <b>full amount up front</b>, <b>every month / 3 months / year</b> (bills are made by themselves) or <b>per visit</b> (added to each visit's job card).",
   "Each visit becomes a job card a week before it is due — it shows on the calendar and the staff phone page.",
   "Contracts ending in 30 days are listed under <b>Ending soon</b>: press [[Ask to renew]] to WhatsApp the customer, then [[Renew]]. You can also [[Pause]] or [[Cancel contract]]."],
  dict(tip="A contract entered late does not create job cards for visits that are already past."))
svc["tasks"].insert(4, AMC_TASK)
# Records on the job card for clinics, labs, optical shops and laundries
svc["tasks"].insert(2, ("Clinic, lab, optical &amp; laundry records",
  ["<b>Clinics</b>: on the job card fill the <b>Visit record</b> — BP, pulse, temperature, weight, SpO₂, sugar, complaint, diagnosis, medicines (dose, how often, days) and advice. Press [[Print prescription]].",
   "Set a <b>Next visit</b> date and press [[Book the next visit]] — a new appointment is made for the same patient and doctor.",
   "<b>Laboratories</b>: enter each test with its result, unit and normal range. Results above or below the range are marked <b>H</b> / <b>L</b>. Press [[Print report]].",
   "<b>Optical shops</b>: open [[👓 Eye tests &amp; orders]], fill the eye power for right and left eye, PD, frame and lens, then [[Print prescription / order]]. The last test of the same customer is shown to compare.",
   "<b>Laundries</b>: add each item with its count (e.g. <i>Shirt – wash &amp; iron × 3</i>); every piece gets its own tag number. Press [[Print tags]]."],
  dict(tip="Only the record for your kind of business is shown on the job card.")))
for _v in VERTICALS:
    if _v.get("slug") == "project-agency":
        _v["tasks"] = [AMC_TASK] + list(_v.get("tasks", []))
