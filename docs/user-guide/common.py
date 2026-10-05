from engine import *

def getting_started():
    S = []

    S.append(("signin","Sign in &amp; sign out", 
      "<p class='sub'>New? Press <b>Start a free trial</b> on the BookPilot website, choose your business type and fill in a short form — a <b>setup wizard</b> then helps you add your logo, first products and printer. Already have an account? You will have a <b>username</b> and <b>password</b>. It works in any browser on a computer, tablet or phone, and can be installed as an app.</p>" +
      steps([("Open your link","You will see the <b>Sign in</b> page: <i>“Manage your business — sales, stock, and reports.”</i>"),
             ("Type your username and password","Then press [[Sign in]]."),
             ("Forgot your password?","Press [[Forgot password?]] under the sign-in button and follow the email link. If no email arrives, message us and we will reset it for you.")]) +
      callouts(note="Want more security? Switch on <b>two-step login</b> under Settings → Security &amp; 2FA.",
               warn="After several wrong attempts you will see <i>“Too many failed attempts. Try again later.”</i> Wait a few minutes and try again.",
               tip="At the bottom-left of the screen you will see your email and <b>Log out</b>. Always log out on shared computers.") ,"🔐"))

    S.append(("screen","Know your screen",
      "<p class='sub'>The menu on the left is your control centre. It always looks like this — plus one extra section for <b>your business type</b>.</p>" +
      '<div class="mock">' + mock("YOUR BUSINESS SECTION", ["e.g. Members / Appointments / Batches / Projects…"]) +
      '<div class="expl"><h3>What each group is for</h3>' +
      table(["Menu","What you do there"],[
        ["Overview","Your dashboard — today’s numbers at a glance"],
        ["Sales","[[Invoices]], [[Quotations]], [[Sales orders &amp; delivery]], [[POS]], [[Returns &amp; Refunds]], [[Coupons]], [[Loyalty]], leads and price lists"],
        ["Purchases","[[Purchase orders]], [[Purchases]], [[Suppliers]], [[Purchase Reports]]"],
        ["Finance","[[Bank &amp; cash]], [[Accounts &amp; reports]], [[Cheques (PDC)]], [[Expenses]], [[Budgets]], [[Daily report]] and [[Billing]] (your subscription)"],
        ["People","[[Customers]], [[Money to collect]], [[Team]] (logins) and [[Staff &amp; HR]] (attendance, payroll)"],
        ["Business","[[Stock &amp; inventory]], [[Analytics]] and [[Branches]]"],
        ["Settings","[[Reminders &amp; alerts]], [[Tax &amp; currency]], [[Devices &amp; Printers]], [[Security &amp; 2FA]], [[Backups]] and [[Settings]]"],
        ["Your business section","The tools made for your type of business — see your business guide"]]) +
      '</div></div>' +
      callouts(note="Some menus (for example Branches or Coupons) may be hidden if they are not part of your plan. If you need one, message us — it can be switched on for you.",
               tip="If you own more than one business, a <b>Switch business</b> list appears at the top of the menu. Click a name to move between them.") ,"🧭"))

    S.append(("dashboard","Your dashboard (Overview)",
      "<p class='sub'>Open <b>Overview</b> after signing in. This is your daily health check.</p>" +
      ticks(["<b>Today’s sales</b> and <b>This month’s revenue</b> — how the business is doing.",
             "<b>Outstanding dues</b> — money customers still owe you.",
             "<b>Low stock items</b> — products that reached their reorder level.",
             "A <b>Business overview</b> row with counters for your business type (members, appointments today, orders pending, batches expiring, active projects…).",
             "A <b>subscription banner</b>: <i>Free trial — N days left</i>, <i>Subscription renews in N days</i> or <i>Your subscription has expired</i>."]) +
      callouts(tip="Make it a habit: open Overview every morning and every closing time."),"📊"))

    S.append(("settings","Set up your business profile",
      "<p class='sub'>Do this first — your name, address and logo appear on invoices.</p>" +
      steps([("Open [[[Settings]]] → [[Settings]]",""),
             ("Fill in the details","<b>Name</b>, <b>Registration number</b> (trade licence / GST / CR), <b>Address</b>, <b>Phone</b>, <b>Email</b>, <b>Default currency</b> and upload your <b>Logo</b>."),
             ("Press [[Save settings]]","You will see <i>“Business settings updated.”</i>")]) +
      callouts(warn="Choose the correct <b>currency</b> now. It is used on invoices and reports.") ,"🏢"))

    S.append(("customers","Customers",
      "<p class='sub'>Everyone who buys from you — or books with you — is a customer.</p>" +
      steps([("Open [[[People]]] → [[Customers]] → [[+ Add customer]]",""),
             ("Enter <b>Name</b>, <b>Phone</b>, <b>Email</b> and <b>Address</b>","Only the name is really needed. Phone helps you find them quickly."),
             ("Save","Use [[Edit]] any time to correct details. [[Export CSV]] downloads the list.")]) +
      callouts(note="A built-in <b>Walk-in Customer</b> is used when you sell to someone without creating a record.",
               warn="You cannot delete a customer who already has sales, appointments or other records — this protects your accounts. Edit the customer instead."),"👥"))

    S.append(("products","Products, categories, brands &amp; units",
      "<p class='sub'>For shops: everything you sell is a product. Set up the small lists first, then products.</p>" +
      steps([("Units","Open [[Units]] and add how you count stock: <b>pcs, kg, box, meter, litre</b>."),
             ("Categories &amp; brands","Open [[Categories]] and [[Brands]] to group products (optional but very helpful for search and reports)."),
             ("Add a product","[[Products]] → [[+ Add product]]. Fill <b>SKU</b>, <b>Name</b>, <b>Category</b>, <b>Brand</b>, <b>Unit</b>, <b>Cost price</b>, <b>Selling price</b>, <b>Reorder level</b>."),
             ("Extra details","Use one line per detail, e.g. <code>Colour: Blue</code> or <code>Size: L</code>."),
             ("Variants","On the product press [[+ Variant]] to create colour/size options with their own SKU and price."),
             ("Barcodes","Press [[Barcode]] on a product, or open [[Print Barcodes]] to print many labels at once.")]) +
      callouts(tip="<b>SKU</b> is your own product code — short and unique, like <i>SHIRT-BL-L</i>. It never repeats.",
               warn="A product that already has sales or stock movements cannot be deleted. Edit it instead."),"📦"))

    S.append(("import","Import &amp; export with Excel (CSV)",
      "<p class='sub'>Add hundreds of products in one go, or download your list to edit in Excel.</p>" +
      steps([("Open [[Products]] and press [[Import CSV]]",""),
             ("Prepare your file","First row must contain these headings: <b>SKU, Name, Unit, Selling Price</b> (required) and optionally <b>Category, Brand, Cost Price, Reorder Level</b>."),
             ("Upload the file","You will see <i>“Imported N new products, updated N existing.”</i> If some rows are wrong, they are skipped and listed so you can fix them.")]) +
      table(["SKU","Name","Unit","Selling Price","Category","Brand","Cost Price","Reorder Level"],
            [["TSH-001","Cotton T-Shirt","pcs","45","Apparel","Zara","28","10"],["RICE-5KG","Basmati Rice 5kg","bag","32","Grocery","","24","20"]]) +
      callouts(tip="Same SKU again = <b>update</b>, not duplicate. Missing categories, brands and units are created automatically.",
               note="Save your Excel sheet as <b>CSV (UTF-8)</b>. Use [[Export CSV]] to get a ready-made template with your current products."),"📥"))

    S.append(("pos","POS — billing at the counter",
      "<p class='sub'>The fastest way to sell. Open [[[Sales]]] → [[POS]].</p>" +
      steps([("Find the product","Type the name or SKU in the search box (or scan the barcode) and click the product. Change the quantity in the cart if needed."),
             ("Choose branch &amp; customer","Pick the <b>Branch</b> if you have several. Leave <b>Walk-in Customer</b> or choose a saved customer."),
             ("Coupon (optional)","Type the <b>Coupon code</b>. The discount is shown before you pay."),
             ("Payment method","Choose <b>Cash</b>, <b>Card</b> or <b>Bank Transfer</b>."),
             ("Press [[Complete Sale]]","You will see <i>“Sale complete — INV-000123”</i> with a <b>Print receipt</b> link. Stock reduces and accounts update instantly.")]) +
      callouts(tip="Named customers automatically earn loyalty points on POS sales.",
               warn="If you see a red message (for example <i>Cart is empty</i> or a stock problem) nothing was saved — fix it and press Complete Sale again.") ,"🧾"))

    S.append(("returns","Returns &amp; refunds",
      "<p class='sub'>Customer brings something back? Never delete the invoice — process a return so stock and accounts stay correct.</p>" +
      steps([("Open [[[Sales]]] → [[Returns &amp; Refunds]] → [[+ New return]]",""),
             ("Enter the invoice number","For example <b>INV-000123</b>, then press [[Find invoice]]."),
             ("Enter <b>Return qty</b> for each item","The screen shows sold quantity and what was already returned."),
             ("Choose the refund","<b>Reason</b>, <b>Refund method</b> (Cash, Card, Bank or Store Credit) and <b>Date</b>. Press [[Process return]]."),
             ("Done","<i>“Return processed and stock updated.”</i> The Returns list and Return reports show totals and top reasons.")]) +
      callouts(warn="You cannot return more than was sold. If the invoice has been fully returned you will see a message saying so."),"↩️"))

    S.append(("coupons","Coupons &amp; loyalty points",
      "<p class='sub'>Reward customers and run offers.</p>" +
      "<h3>Coupons</h3>" +
      steps([("Open [[[Sales]]] → [[Coupons]] → [[+ Add coupon]]",""),
             ("Fill the coupon","<b>Code</b> (e.g. EID10), <b>Discount type</b> (<i>Percentage</i> or <i>Fixed Amount</i>), <b>Discount value</b>, <b>Min purchase</b>, <b>Max discount</b>, <b>Start date</b>, <b>Expiry date</b>, <b>Usage limit</b>."),
             ("Switch it on or off","Use [[Activate]] / [[Deactivate]] beside any coupon."),
             ("Use it","Type the code on the POS screen.")]) +
      "<h3>Loyalty points</h3>" +
      "<p>Customers with a saved profile earn points automatically at checkout — by default <b>1 point for every 10 spent</b>. Open [[[Sales]]] → [[Loyalty]] to see balances, and press [[Redeem points]] to use points (customer, points, reason).</p>" +
      callouts(note="Points are not given on Walk-in sales because there is no customer to credit. If you want a different earning rate, ask us."),"🎁"))

    S.append(("purchases","Suppliers &amp; purchases",
      "<p class='sub'>Record stock you buy and money you owe.</p>" +
      steps([("Add a supplier","[[[Purchases]]] → [[Suppliers]] → [[+ Add supplier]] (name, phone, email, address)."),
             ("Record a purchase","[[Purchases]] → [[+ New purchase]]. Choose <b>Supplier</b>, <b>Product</b>, <b>Branch/Warehouse</b>, <b>Quantity</b>, <b>Unit cost</b>, <b>Bill number</b> and <b>Date</b>. You will see <i>“Purchase recorded and stock updated.”</i>"),
             ("Pay a supplier","Open [[Suppliers]] → click the supplier name → [[+ Record payment]]. Enter <b>Amount</b>, <b>Date</b>, <b>Method</b> (Cash/Bank) and optionally the bill it is for."),
             ("Check totals","Open [[Purchase Reports]]: total purchased, total paid, outstanding, and totals by supplier.")]) +
      callouts(tip="Record the supplier’s bill number — it makes checking statements easy."),"🚚"))

    S.append(("expenses","Expenses",
      "<p class='sub'>Rent, salaries, electricity, transport — record every cost so your profit is true.</p>" +
      steps([("Add categories once","[[[Finance]]] → [[Expenses]] → [[Categories]]. Press [[+ Add common categories (Rent, Salary, etc.)]] to add the usual ones instantly, or [[+ Add category]] for your own."),
             ("Record an expense","[[+ Add expense]] → choose <b>Category</b>, <b>Date</b>, <b>Amount</b>, <b>Description</b> and <b>Payment method</b> (Cash or Bank). You will see <i>“Expense recorded.”</i>"),
             ("Review","Open the expense reports from the Expenses page to see total expenses and totals by category.")]) +
      callouts(note="Every expense is posted to your books automatically."),"💸"))

    S.append(("team","Team &amp; roles (staff logins)",
      "<p class='sub'>Give each staff member their own login. Decide what each person can see and do.</p>" +
      table(["Role","What it is for"],[
        ["<b>Owner</b>","Full access — reports, roles, team, billing"],
        ["<b>Accountant</b>","Accounting, sales, purchases, expenses, banking, payroll"],
        ["<b>Staff</b>","Everyday work: create invoices, manage stock, customers"]]) +
      steps([("Add a login","[[[People]]] → [[Team]] → [[+ Add team member]]. Enter <b>Username</b>, <b>Email</b>, <b>Password</b> (minimum 8 characters) and choose a <b>Role</b>. You will see <i>“… added as Staff.”</i>"),
             ("Change a role or remove someone","On the Team page use [[Change role]] or [[Remove]]. You cannot remove yourself."),
             ("Make a custom role (e.g. Cashier)","[[Manage roles]] → [[+ Create custom role]] → name it → [[Edit permissions]] and tick exactly what they may do → [[Save permissions]].")]) +
      callouts(warn="The three system roles (Owner, Accountant, Staff) cannot be edited — create a custom role instead.",
               note="Your plan has a maximum number of users. If you reach it, ask us to upgrade.<br><b>Staff</b> under a business section (like Spa or Saloon) is different: it is the list of people who <i>do the work</i> (therapists, stylists). They do not need a login.") ,"🛡️"))

    S.append(("branches","Branches &amp; stock by branch",
      "<p class='sub'>More than one shop or warehouse? Keep stock separate.</p>" +
      steps([("Add a branch","[[[Business]]] → [[Branches]] → [[+ Add branch]]. Enter <b>Name</b>, <b>Address</b>, <b>Phone</b>, <b>Manager name</b> and tick <b>Is default</b> for your main one."),
             ("Sell and buy per branch","Choose the branch on the POS and in Purchases."),
             ("Compare stock","Press [[Stock by branch]] to see each product’s stock in every branch and the total.")]) +
      callouts(warn="You cannot delete your only branch, or a branch that already has records."),"🏬"))

    S.append(("reports","Analytics &amp; reports",
      "<p class='sub'>Know how the business is doing without an accountant.</p>" +
      table(["Where","What you see"],[
        ["[[[Business]]] → [[Analytics]]","Sales, Expenses, Net profit, Invoices, <b>Sales by day</b> chart, <b>Payment methods</b> chart, <b>Top-selling products</b>"],
        ["[[Purchase Reports]]","Total purchased, paid, outstanding, by supplier"],
        ["Expenses page → reports","Total expenses and by category"],
        ["Returns page → reports","Total refunded, number of returns, top reasons"],
        ["Your business section → [[Reports]]","Reports designed for your business (see your business guide)"]]) +
      callouts(tip="Open Analytics on the 1st of every month — compare sales with expenses to see real profit."),"📈"))

    S.append(("billing","Your subscription &amp; billing",
      "<p class='sub'>Only the <b>Owner</b> can pay or submit a payment.</p>" +
      steps([("See your plan","Open [[[Finance]]] → [[Billing]]: current plan, price, users allowed, days remaining and payment history."),
             ("Pay by card","Press <b>Pay now</b> and pay by card, Apple Pay or Google Pay on the secure payment page. Your subscription updates automatically."),
             ("Paid by bank transfer or cash?","Fill in <b>Amount</b>, <b>Method</b>, <b>Reference</b> and <b>Notes</b>, then press [[Submit payment]]. We confirm it and your subscription is renewed."),
             ("Trial &amp; expiry","During a free trial the dashboard shows the days left. After expiry, submit a payment to continue.")]) +
      callouts(note="Card payment is only offered in countries where it is set up. Otherwise use bank transfer and submit the reference."),"💳"))

    S.append(("notifications","Notifications",
      "<p class='sub'>The bell of your business — open [[[Settings]]] → [[Notifications]].</p>" +
      ticks(["<b>Low stock</b> when a product reaches its reorder level.",
             "<b>Overdue invoices</b> that are still unpaid.",
             "<b>Subscription</b> expiring soon or expired.",
             "<b>Medicine / supplement batches</b> nearing expiry (pharmacy and protein shops)."]) +
      "<p>Press [[Mark all as read]] to clear them.</p>","🔔"))
    return S

def help_sections():
    S = []
    S.append(("msgs","What the messages mean",
       "<p class='sub'>Red or yellow messages appear at the top of the page. They tell you exactly what to fix.</p>" +
       table(["You see","What it means","What to do"],[
         ["You don’t have permission to do that.","Your role is not allowed to do this action.","Ask the business Owner to change your role or permissions (Team → Change role)."],
         ["This feature isn’t enabled for your account. Contact support.","That tool is not part of your plan.","Message us — we can switch it on."],
         ["Can’t delete — … linked to it.","The item is already used in sales, stock or appointments.","Edit it instead. Deleting used records would break your accounts."],
         ["This unit isn’t available to sell.","The phone or cycle is already sold, returned or under repair.","Check its status on the Units page."],
         ["Only N remaining in batch …","You tried to sell more than the batch holds.","Enter a smaller quantity or pick another batch."],
         ["Batch … expired on …, cannot dispense.","The batch is past its expiry date.","Remove it from stock; use another batch."],
         ["Can’t return more than N of …","You are returning more than was sold.","Enter a quantity up to the sold quantity."],
         ["That username is already taken / A user with that email already exists.","Every login must be unique.","Use a different username or email."],
         ["Invalid username or password. / Too many failed attempts.","Wrong details, or too many tries.","Check caps-lock; wait a few minutes; or use Forgot password."],
         ["Your subscription has expired.","The plan period ended.","Open Billing and pay or submit a payment."],
         ["Your login isn’t linked to a company yet.","Your login has no business attached.","Message us — we will link it."]]), "💬"))
    S.append(("faq","Frequently asked questions",
       faq("Can I use it on my phone?","Yes. Open the website on your phone and press <b>Install app</b>, or install the Android / iPhone app. The POS and kitchen screens also work on tablets.") +
       faq("Can I use it in my language?","Yes — 12 languages including Malayalam, Arabic, Hindi, Urdu, Tamil and more. Press 🌐 at the top-right. Each person can choose their own language.") +
       faq("Can two or more people work at the same time?","Yes. Give each person their own login under <b>People → Team</b> so you always know who did what.") +
       faq("I made a mistake in a sale. Can I edit or delete the invoice?","To keep your accounts correct, invoices are not deleted. Use <b>Returns &amp; Refunds</b> for the wrong sale and sell again correctly.") +
       faq("Is my data safe? Can other businesses see my data?","No. Each business is completely separate — you only ever see your own company’s data. Do not share your password; give each staff member their own login.") +
       faq("Where do I print an invoice or receipt?","After a POS sale press <b>Print receipt</b>. For older sales open the sales list and press <b>PDF</b>.") +
       faq("How do I get my data into Excel?","Most lists have an <b>Excel</b> or <b>Export CSV</b> button. To download everything, use Settings → Backup &amp; export → <b>Download all my data</b>.") +
       faq("What if the internet stops?","The POS keeps working offline and syncs your bills when the connection is back.") +
       faq("Can I add a new branch or another business later?","Branches: <b>Business → Branches</b>. A separate business can be added by us — message us.") +
       faq("Who can see reports and money?","Only roles with permission. The Staff role cannot see financial reports by default."), "❓"))
    S.append(("contact","Contact us",
       f'<p class="sub">When you message us, please send:</p>' + ticks(["Your <b>business name</b> and <b>username</b>.","A <b>screenshot</b> of the screen and the red/yellow message.","What you were trying to do, in one line."]) +
       f'<p><b>WhatsApp / Call:</b> {CONFIG["WHATSAPP"]}<br><b>Email:</b> <a href="mailto:{CONFIG["EMAIL"]}">{CONFIG["EMAIL"]}</a></p>', "📞"))
    return S
