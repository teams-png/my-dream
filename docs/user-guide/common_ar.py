from engine import *

def getting_started():
    S = []
    S.append(("signin","تسجيل الدخول والخروج",
      "<p class='sub'>جديد؟ اضغط <b>Start a free trial</b> في موقع BookPilot، واختر نوع عملك واملأ نموذجاً قصيراً — ثم يساعدك <b>معالج الإعداد</b> على إضافة شعارك وأول منتجاتك والطابعة. لديك حساب؟ استخدم <b>اسم المستخدم</b> و<b>كلمة المرور</b>. يعمل في أي متصفح على الكمبيوتر أو التابلت أو الهاتف، ويمكن تثبيته كتطبيق.</p>" +
      steps([("افتح الرابط الخاص بك","ستظهر صفحة <b>Sign in</b>: <i>“Manage your business — sales, stock, and reports.”</i>"),
             ("اكتب اسم المستخدم وكلمة المرور","ثم اضغط [[Sign in]]."),
             ("نسيت كلمة المرور؟","اضغط [[Forgot password?]] أسفل زر الدخول واتبع الرابط الذي يصلك بالبريد. إن لم يصل البريد راسلنا وسنعيد ضبطها لك.")]) +
      callouts(warn="بعد عدة محاولات خاطئة ستظهر رسالة <i>“Too many failed attempts. Try again later.”</i> انتظر بضع دقائق ثم حاول مجدداً.",
               tip="في أسفل الشاشة ستجد بريدك الإلكتروني وزر <b>Log out</b>. سجّل الخروج دائماً على الأجهزة المشتركة."),"🔐"))

    S.append(("screen","تعرّف على الشاشة",
      "<p class='sub'>القائمة الجانبية هي مركز التحكم لديك. تبدو دائماً هكذا، مع قسم إضافي خاص <b>بنوع عملك</b>.</p>" +
      '<div class="mock">' + mock("YOUR BUSINESS SECTION", ["e.g. Members / Appointments / Batches / Projects…"]) +
      '<div class="expl"><h3>وظيفة كل مجموعة</h3>' +
      table(["القائمة","ماذا تفعل فيها"],[
        ["Overview","لوحتك الرئيسية — أرقام اليوم في نظرة واحدة"],
        ["Sales","[[POS]] الفوترة عند الكاشير، [[Returns &amp; Refunds]]، [[Coupons]]، [[Loyalty]]"],
        ["Purchases","[[Purchases]] من الموردين، [[Suppliers]]، [[Purchase Reports]]"],
        ["Finance","[[Expenses]] (الإيجار والرواتب والفواتير)، [[Billing]] (اشتراكك)"],
        ["People","[[Customers]] و[[Team]] (حسابات الموظفين والأدوار)"],
        ["Business","مخططات [[Analytics]] و[[Branches]]"],
        ["Settings","[[Notifications]] و[[Settings]] (ملف النشاط التجاري)"],
        ["قسم عملك","الأدوات المصممة لنوع عملك — راجع دليل عملك"]]) +
      '</div></div>' +
      callouts(note="قد تختفي بعض القوائم (مثل Branches أو Coupons) إن لم تكن ضمن باقتك. إن احتجتها راسلنا وسنفعّلها لك.",
               tip="إذا كنت تملك أكثر من نشاط تجاري، تظهر قائمة <b>Switch business</b> أعلى القائمة. اضغط على الاسم للتنقل."),"🧭"))

    S.append(("dashboard","لوحتك الرئيسية (Overview)",
      "<p class='sub'>افتح <b>Overview</b> بعد تسجيل الدخول. إنها الفحص اليومي لصحة عملك.</p>" +
      ticks(["<b>Today’s sales</b> و<b>This month’s revenue</b> — كيف يسير العمل.",
             "<b>Outstanding dues</b> — المبالغ التي لم يدفعها العملاء بعد.",
             "<b>Low stock items</b> — المنتجات التي وصلت إلى حد إعادة الطلب.",
             "صف <b>Business overview</b> بعدّادات خاصة بنوع عملك (الأعضاء، مواعيد اليوم، الطلبات المعلقة، الدُفعات المنتهية قريباً، المشاريع النشطة…).",
             "<b>شريط الاشتراك</b>: <i>Free trial — N days left</i> أو <i>Subscription renews in N days</i> أو <i>Your subscription has expired</i>."]) +
      callouts(tip="اجعل فتح Overview عادة كل صباح وعند الإغلاق."),"📊"))

    S.append(("settings","إعداد ملف نشاطك التجاري",
      "<p class='sub'>افعل هذا أولاً — اسمك وعنوانك وشعارك يظهرون على الفواتير.</p>" +
      steps([("افتح [[[Settings]]] ← [[Settings]]",""),
             ("املأ البيانات","<b>Name</b> و<b>Registration number</b> (الرخصة التجارية / السجل التجاري) و<b>Address</b> و<b>Phone</b> و<b>Email</b> و<b>Default currency</b> وارفع <b>Logo</b>."),
             ("اضغط [[Save settings]]","ستظهر <i>“Business settings updated.”</i>")]) +
      callouts(warn="اختر <b>العملة</b> الصحيحة الآن، فهي تُستخدم في الفواتير والتقارير."),"🏢"))

    S.append(("customers","العملاء",
      "<p class='sub'>كل من يشتري منك — أو يحجز لديك — هو عميل.</p>" +
      steps([("افتح [[[People]]] ← [[Customers]] ← [[+ Add customer]]",""),
             ("أدخل <b>Name</b> و<b>Phone</b> و<b>Email</b> و<b>Address</b>","الاسم وحده يكفي عملياً. رقم الهاتف يساعدك على إيجاده بسرعة."),
             ("احفظ","استخدم [[Edit]] لتصحيح البيانات في أي وقت. [[Export CSV]] يحمّل القائمة.")]) +
      callouts(note="يوجد <b>Walk-in Customer</b> مدمج يُستخدم عند البيع لشخص دون إنشاء سجل له.",
               warn="لا يمكن حذف عميل لديه مبيعات أو مواعيد أو سجلات أخرى — هذا يحمي حساباتك. عدّل بياناته بدلاً من ذلك."),"👥"))

    S.append(("products","المنتجات والفئات والعلامات والوحدات",
      "<p class='sub'>للمتاجر: كل ما تبيعه هو منتج. جهّز القوائم الصغيرة أولاً ثم المنتجات.</p>" +
      steps([("Units","افتح [[Units]] وأضف طريقة عدّ المخزون: <b>pcs, kg, box, meter, litre</b>."),
             ("Categories وBrands","افتح [[Categories]] و[[Brands]] لتجميع المنتجات (اختياري لكنه مفيد جداً للبحث والتقارير)."),
             ("أضف منتجاً","[[Products]] ← [[+ Add product]]. املأ <b>SKU</b> و<b>Name</b> و<b>Category</b> و<b>Brand</b> و<b>Unit</b> و<b>Cost price</b> و<b>Selling price</b> و<b>Reorder level</b>."),
             ("Extra details","سطر لكل تفصيل، مثل <code>Colour: Blue</code> أو <code>Size: L</code>."),
             ("Variants","اضغط [[+ Variant]] على المنتج لإنشاء خيارات اللون/المقاس، لكل منها SKU وسعر خاص."),
             ("Barcodes","اضغط [[Barcode]] على المنتج، أو افتح [[Print Barcodes]] لطباعة عدة ملصقات دفعة واحدة.")]) +
      callouts(tip="<b>SKU</b> هو رمز المنتج الخاص بك — قصير وفريد مثل <i>SHIRT-BL-L</i>، ولا يتكرر أبداً.",
               warn="لا يمكن حذف منتج له مبيعات أو حركات مخزون. عدّله بدلاً من ذلك."),"📦"))

    S.append(("import","الاستيراد والتصدير عبر Excel (CSV)",
      "<p class='sub'>أضف مئات المنتجات دفعة واحدة، أو نزّل قائمتك وعدّلها في Excel.</p>" +
      steps([("افتح [[Products]] واضغط [[Import CSV]]",""),
             ("جهّز الملف","يجب أن يحتوي الصف الأول على هذه العناوين: <b>SKU, Name, Unit, Selling Price</b> (إلزامية) واختيارياً <b>Category, Brand, Cost Price, Reorder Level</b>."),
             ("ارفع الملف","ستظهر <i>“Imported N new products, updated N existing.”</i> الصفوف الخاطئة تُتجاوز وتُعرض لتصححها.")]) +
      table(["SKU","Name","Unit","Selling Price","Category","Brand","Cost Price","Reorder Level"],
            [["TSH-001","Cotton T-Shirt","pcs","45","Apparel","Zara","28","10"],["RICE-5KG","Basmati Rice 5kg","bag","32","Grocery","","24","20"]]) +
      callouts(tip="نفس الـ SKU مرة أخرى = <b>تحديث</b> وليس تكراراً. الفئات والعلامات والوحدات غير الموجودة تُنشأ تلقائياً.",
               note="احفظ ملف Excel بصيغة <b>CSV (UTF-8)</b>. استخدم [[Export CSV]] للحصول على قالب جاهز بمنتجاتك الحالية."),"📥"))

    S.append(("pos","نقطة البيع POS — الفوترة عند الكاشير",
      "<p class='sub'>أسرع طريقة للبيع. افتح [[[Sales]]] ← [[POS]].</p>" +
      steps([("ابحث عن المنتج","اكتب الاسم أو الـ SKU في مربع البحث (أو امسح الباركود) ثم اضغط على المنتج. غيّر الكمية في السلة عند الحاجة."),
             ("الفرع والعميل","اختر <b>Branch</b> إن كانت لديك فروع. اترك <b>Walk-in Customer</b> أو اختر عميلاً محفوظاً."),
             ("الكوبون (اختياري)","اكتب <b>Coupon code</b>. يظهر الخصم قبل الدفع."),
             ("طريقة الدفع","اختر <b>Cash</b> أو <b>Card</b> أو <b>Bank Transfer</b>."),
             ("اضغط [[Complete Sale]]","ستظهر <i>“Sale complete — INV-000123”</i> مع رابط <b>Print receipt</b>. ينخفض المخزون وتتحدث الحسابات فوراً.")]) +
      callouts(tip="العملاء المحفوظون يكسبون نقاط ولاء تلقائياً على مبيعات POS.",
               warn="إذا ظهرت رسالة حمراء (مثل <i>Cart is empty</i> أو مشكلة مخزون) فلم يُحفظ شيء — صحّح ثم اضغط Complete Sale مجدداً."),"🧾"))

    S.append(("returns","المرتجعات والاسترداد",
      "<p class='sub'>أعاد العميل بضاعة؟ لا تحذف الفاتورة أبداً — نفّذ مرتجعاً ليبقى المخزون والحسابات صحيحين.</p>" +
      steps([("افتح [[[Sales]]] ← [[Returns &amp; Refunds]] ← [[+ New return]]",""),
             ("أدخل رقم الفاتورة","مثل <b>INV-000123</b>، ثم اضغط [[Find invoice]]."),
             ("أدخل <b>Return qty</b> لكل صنف","تعرض الشاشة الكمية المباعة وما أُرجع سابقاً."),
             ("اختر طريقة الاسترداد","<b>Reason</b> و<b>Refund method</b> (Cash أو Card أو Bank أو Store Credit) و<b>Date</b>. اضغط [[Process return]]."),
             ("انتهى الأمر","<i>“Return processed and stock updated.”</i> تعرض قائمة المرتجعات وتقريرها الإجمالي وأهم الأسباب.")]) +
      callouts(warn="لا يمكنك إرجاع أكثر مما بِيع. وإن أُرجعت الفاتورة بالكامل فستظهر رسالة بذلك."),"↩️"))

    S.append(("coupons","الكوبونات ونقاط الولاء",
      "<p class='sub'>كافئ عملاءك ونفّذ العروض.</p>" +
      "<h3>الكوبونات</h3>" +
      steps([("افتح [[[Sales]]] ← [[Coupons]] ← [[+ Add coupon]]",""),
             ("املأ بيانات الكوبون","<b>Code</b> (مثل EID10) و<b>Discount type</b> (<i>Percentage</i> أو <i>Fixed Amount</i>) و<b>Discount value</b> و<b>Min purchase</b> و<b>Max discount</b> و<b>Start date</b> و<b>Expiry date</b> و<b>Usage limit</b>."),
             ("التفعيل والإيقاف","استخدم [[Activate]] / [[Deactivate]] بجانب أي كوبون."),
             ("الاستخدام","اكتب الرمز في شاشة POS.")]) +
      "<h3>نقاط الولاء</h3>" +
      "<p>العملاء المحفوظون يكسبون النقاط تلقائياً عند الدفع — افتراضياً <b>نقطة واحدة لكل 10 يُنفقها العميل</b>. افتح [[[Sales]]] ← [[Loyalty]] لرؤية الأرصدة، واضغط [[Redeem points]] لاستخدام النقاط (customer, points, reason).</p>" +
      callouts(note="لا تُمنح نقاط على مبيعات Walk-in لعدم وجود عميل. إن أردت معدلاً مختلفاً فاطلب منا ذلك."),"🎁"))

    S.append(("purchases","الموردون والمشتريات",
      "<p class='sub'>سجّل المخزون الذي تشتريه والمبالغ التي عليك.</p>" +
      steps([("أضف مورداً","[[[Purchases]]] ← [[Suppliers]] ← [[+ Add supplier]] (الاسم والهاتف والبريد والعنوان)."),
             ("سجّل عملية شراء","[[Purchases]] ← [[+ New purchase]]. اختر <b>Supplier</b> و<b>Product</b> و<b>Branch/Warehouse</b> وأدخل <b>Quantity</b> و<b>Unit cost</b> و<b>Bill number</b> و<b>Date</b>. ستظهر <i>“Purchase recorded and stock updated.”</i>"),
             ("ادفع للمورد","[[Suppliers]] ← اضغط اسم المورد ← [[+ Record payment]]. أدخل <b>Amount</b> و<b>Date</b> و<b>Method</b> (Cash/Bank) واختيارياً الفاتورة المقصودة."),
             ("راجع الإجماليات","افتح [[Purchase Reports]]: إجمالي المشتريات والمدفوع والمتبقي والإجمالي لكل مورد.")]) +
      callouts(tip="سجّل رقم فاتورة المورد — يسهّل مطابقة كشوف الحساب."),"🚚"))

    S.append(("expenses","المصروفات",
      "<p class='sub'>الإيجار والرواتب والكهرباء والنقل — سجّل كل تكلفة ليكون ربحك حقيقياً.</p>" +
      steps([("أضف الفئات مرة واحدة","[[[Finance]]] ← [[Expenses]] ← [[Categories]]. اضغط [[+ Add common categories (Rent, Salary, etc.)]] لإضافة الفئات المعتادة فوراً، أو [[+ Add category]] لفئتك الخاصة."),
             ("سجّل مصروفاً","[[+ Add expense]] ← اختر <b>Category</b> و<b>Date</b> و<b>Amount</b> و<b>Description</b> و<b>Payment method</b> (Cash أو Bank). ستظهر <i>“Expense recorded.”</i>"),
             ("راجع","افتح تقرير المصروفات من صفحة Expenses لرؤية إجمالي المصروفات وإجمالي كل فئة.")]) +
      callouts(note="كل مصروف يُرحَّل تلقائياً إلى حساباتك."),"💸"))

    S.append(("team","الفريق والأدوار (حسابات الموظفين)",
      "<p class='sub'>امنح كل موظف حسابه الخاص، وحدّد ما يمكن لكل شخص رؤيته وفعله.</p>" +
      table(["الدور","الغرض منه"],[
        ["<b>Owner</b>","وصول كامل — التقارير والأدوار والفريق والفواتير"],
        ["<b>Accountant</b>","المحاسبة والمبيعات والمشتريات والمصروفات والبنوك والرواتب"],
        ["<b>Staff</b>","العمل اليومي: إنشاء الفواتير وإدارة المخزون والعملاء"]]) +
      steps([("أضف حساباً","[[[People]]] ← [[Team]] ← [[+ Add team member]]. أدخل <b>Username</b> و<b>Email</b> و<b>Password</b> (8 أحرف على الأقل) واختر <b>Role</b>. ستظهر <i>“… added as Staff.”</i>"),
             ("غيّر دوراً أو أزل شخصاً","في صفحة Team استخدم [[Change role]] أو [[Remove]]. لا يمكنك إزالة نفسك."),
             ("أنشئ دوراً مخصصاً (مثل Cashier)","[[Manage roles]] ← [[+ Create custom role]] ← اكتب الاسم ← [[Edit permissions]] وحدّد بالضبط ما يُسمح له ← [[Save permissions]].")]) +
      callouts(warn="الأدوار الثلاثة الأساسية (Owner وAccountant وStaff) لا يمكن تعديلها — أنشئ دوراً مخصصاً بدلاً منها.",
               note="لباقتك حد أقصى لعدد المستخدمين. إذا بلغته فاطلب منا الترقية.<br><b>Staff</b> داخل قسم عملك (مثل Spa أو Saloon) شيء مختلف: هي قائمة الأشخاص الذين <i>ينفذون العمل</i> (المعالجون والمصففون) ولا يحتاجون إلى حساب دخول."),"🛡️"))

    S.append(("branches","الفروع والمخزون حسب الفرع",
      "<p class='sub'>لديك أكثر من متجر أو مستودع؟ احتفظ بمخزون كل فرع منفصلاً.</p>" +
      steps([("أضف فرعاً","[[[Business]]] ← [[Branches]] ← [[+ Add branch]]. أدخل <b>Name</b> و<b>Address</b> و<b>Phone</b> و<b>Manager name</b> وحدّد <b>Is default</b> للفرع الرئيسي."),
             ("بِع واشترِ حسب الفرع","اختر الفرع في POS وفي Purchases."),
             ("قارن المخزون","اضغط [[Stock by branch]] لرؤية مخزون كل منتج في كل فرع والإجمالي.")]) +
      callouts(warn="لا يمكنك حذف فرعك الوحيد، ولا فرعاً لديه سجلات."),"🏬"))

    S.append(("reports","التحليلات والتقارير",
      "<p class='sub'>اعرف كيف يسير عملك دون الحاجة إلى محاسب.</p>" +
      table(["أين","ماذا ترى"],[
        ["[[[Business]]] ← [[Analytics]]","Sales وExpenses وNet profit وInvoices، ومخطط <b>Sales by day</b> ومخطط <b>Payment methods</b> و<b>Top-selling products</b>"],
        ["[[Purchase Reports]]","إجمالي المشتريات والمدفوع والمتبقي لكل مورد"],
        ["صفحة Expenses ← التقرير","إجمالي المصروفات وحسب الفئة"],
        ["صفحة Returns ← التقرير","إجمالي المستردّ وعدد المرتجعات وأهم الأسباب"],
        ["قسم عملك ← [[Reports]]","تقارير مصممة لعملك (راجع دليل عملك)"]]) +
      callouts(tip="افتح Analytics في الأول من كل شهر — قارن المبيعات بالمصروفات لترى الربح الحقيقي."),"📈"))

    S.append(("billing","اشتراكك والفواتير",
      "<p class='sub'>يمكن لـ <b>Owner</b> فقط الدفع أو تقديم دفعة.</p>" +
      steps([("اطّلع على باقتك","[[[Finance]]] ← [[Billing]]: الباقة الحالية والسعر وعدد المستخدمين المسموح والأيام المتبقية وسجل الدفعات."),
             ("ادفع بالبطاقة","اضغط <b>Pay now</b> وادفع بالبطاقة أو Apple Pay أو Google Pay في صفحة الدفع الآمنة. يتحدث اشتراكك تلقائياً."),
             ("دفعت بتحويل بنكي أو نقداً؟","املأ <b>Amount</b> و<b>Method</b> و<b>Reference</b> و<b>Notes</b> ثم اضغط [[Submit payment]]. نؤكدها ونجدد اشتراكك."),
             ("الفترة التجريبية والانتهاء","خلال الفترة التجريبية تعرض اللوحة الأيام المتبقية. بعد الانتهاء قدّم دفعة للاستمرار.")]) +
      callouts(note="الدفع بالبطاقة متاح فقط في الدول التي جرى إعداده فيها. وإلا فاستخدم التحويل البنكي وقدّم المرجع."),"💳"))

    S.append(("notifications","الإشعارات",
      "<p class='sub'>جرس عملك — افتح [[[Settings]]] ← [[Notifications]].</p>" +
      ticks(["<b>Low stock</b> عندما يصل منتج إلى حد إعادة الطلب.",
             "<b>Overdue invoices</b> — الفواتير المتأخرة غير المدفوعة.",
             "<b>Subscription</b> — اقتراب انتهاء الاشتراك أو انتهاؤه.",
             "<b>دفعات الأدوية / المكملات</b> التي يقترب انتهاؤها (الصيدلية ومتجر البروتين)."]) +
      "<p>اضغط [[Mark all as read]] لمسحها.</p>","🔔"))
    return S

def help_sections():
    S = []
    S.append(("msgs","معنى الرسائل",
       "<p class='sub'>تظهر الرسائل الحمراء أو الصفراء أعلى الصفحة. وهي تخبرك بالضبط بما يجب إصلاحه.</p>" +
       table(["ما تراه","معناه","ما تفعله"],[
         ["You don’t have permission to do that.","دورك غير مسموح له بهذا الإجراء.","اطلب من مالك النشاط (Owner) تغيير دورك (Team ← Change role)."],
         ["This feature isn’t enabled for your account. Contact support.","هذه الأداة ليست ضمن باقتك.","راسلنا وسنفعّلها."],
         ["Can’t delete — … linked to it.","العنصر مستخدم بالفعل في مبيعات أو مخزون أو مواعيد.","عدّله بدلاً من حذفه. حذف السجلات المستخدمة يفسد حساباتك."],
         ["This unit isn’t available to sell.","الجوال أو الدراجة بيعت أو أُرجعت أو قيد الإصلاح.","راجع حالتها في صفحة Units."],
         ["Only N remaining in batch …","حاولت بيع أكثر مما في الدفعة.","أدخل كمية أقل أو اختر دفعة أخرى."],
         ["Batch … expired on …, cannot dispense.","الدفعة تجاوزت تاريخ الانتهاء.","أزلها من المخزون واستخدم دفعة أخرى."],
         ["Can’t return more than N of …","تحاول إرجاع أكثر مما بِيع.","أدخل كمية لا تتجاوز المباعة."],
         ["That username is already taken / A user with that email already exists.","يجب أن يكون كل حساب فريداً.","استخدم اسم مستخدم أو بريداً آخر."],
         ["Invalid username or password. / Too many failed attempts.","بيانات خاطئة أو محاولات كثيرة.","تحقق من Caps-lock، انتظر بضع دقائق، أو استخدم Forgot password."],
         ["Your subscription has expired.","انتهت مدة الباقة.","افتح Billing وادفع أو قدّم دفعة."],
         ["Your login isn’t linked to a company yet.","حسابك غير مرتبط بنشاط تجاري.","راسلنا وسنربطه."]]),"💬"))
    S.append(("faq","أسئلة شائعة",
       faq("هل يمكنني استخدامه على هاتفي؟","نعم. افتح الموقع على هاتفك واضغط <b>Install app</b>، أو ثبّت تطبيق Android / iPhone. شاشات نقطة البيع والمطبخ تعمل أيضاً على التابلت.") +
       faq("هل يمكنني استخدامه بلغتي؟","نعم — 12 لغة منها العربية والإنجليزية والمالايالامية والهندية والأردية. اضغط 🌐 أعلى الشاشة. يختار كل شخص لغته.") +
       faq("هل يمكن لشخصين أو أكثر العمل في الوقت نفسه؟","نعم. امنح كل شخص حسابه الخاص من <b>People ← Team</b> لتعرف دائماً من فعل ماذا.") +
       faq("أخطأت في عملية بيع. هل يمكنني تعديل الفاتورة أو حذفها؟","للحفاظ على صحة حساباتك لا تُحذف الفواتير. استخدم <b>Returns &amp; Refunds</b> للبيع الخاطئ ثم أعد البيع بشكل صحيح.") +
       faq("هل بياناتي آمنة؟ وهل يمكن لأنشطة أخرى رؤيتها؟","لا. كل نشاط منفصل تماماً — ترى بيانات شركتك فقط. لا تشارك كلمة المرور، وامنح كل موظف حسابه الخاص.") +
       faq("أين أطبع الفاتورة أو الإيصال؟","بعد بيع POS اضغط <b>Print receipt</b>. للمبيعات الأقدم افتح قائمة المبيعات واضغط <b>PDF</b>.") +
       faq("كيف أنقل بياناتي إلى Excel؟","استخدم <b>Export CSV</b> في صفحات Products وCustomers وSales ثم افتح الملف في Excel.") +
       faq("هل يمكنني إضافة فرع أو نشاط آخر لاحقاً؟","الفروع: <b>Business ← Branches</b>. أما إضافة نشاط تجاري منفصل فنقوم بها نحن — راسلنا.") +
       faq("من يمكنه رؤية التقارير والأموال؟","الأدوار المصرّح لها فقط. دور Staff لا يرى التقارير المالية افتراضياً."),"❓"))
    S.append(("contact","تواصل معنا",
       '<p class="sub">عند مراسلتنا أرسل لنا من فضلك:</p>' + ticks(["<b>اسم نشاطك</b> و<b>اسم المستخدم</b>.","<b>لقطة شاشة</b> للصفحة والرسالة الحمراء/الصفراء.","ما كنت تحاول فعله في سطر واحد."]) +
       f'<p><b>WhatsApp / Call:</b> <span dir="ltr">{CONFIG["WHATSAPP"]}</span><br><b>Email:</b> <a href="mailto:{CONFIG["EMAIL"]}">{CONFIG["EMAIL"]}</a></p>', "📞"))
    return S
