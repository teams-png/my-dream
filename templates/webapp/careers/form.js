/* BookPilot recruitment form — works on any website (WordPress: "Custom HTML" block, Elementor: "HTML" widget).
   <div class="bookpilot-form"></div>
   <script src="…/careers/<name>/form.js" defer></script>
   Optional attributes on the <div>: data-lang="en|ar", data-job="<job id or title>", data-color="#0f766e",
   data-thanks="https://your-site/thank-you", data-title="Apply now" */
(function () {
  "use strict";
  var CFG = {{ cfg|safe }};
  var T = {
    en: {title: "Job application", personal: "Personal details", contact: "Contact", passport: "Passport", work: "Job & experience",
         docs: "CV & documents", name: "Full name (as in passport)", gender: "Gender", male: "Male", female: "Female",
         dob: "Date of birth", nationality: "Nationality", marital: "Marital status", single: "Single", married: "Married",
         phone: "Mobile / WhatsApp number", email: "Email", location: "Current location (city, country)",
         ppno: "Passport number", ppexp: "Passport expiry date", position: "Position applying for", any: "Any suitable job",
         other: "Other (type below)", trade: "Your trade / skill", exp: "Total experience (years)", gulf: "Gulf experience?",
         yes: "Yes", no: "No", edu: "Highest qualification", langs: "Languages", licence: "Driving licence",
         none: "None", indian: "Home country", gcc: "GCC licence", salary: "Expected salary (per month)",
         notice: "When can you join?", now: "Immediately", m1: "Within 1 month", m2: "1–3 months",
         cv: "CV / resume (PDF, Word or photo, max 8 MB)", msg: "Anything else? (optional)",
         consent: "I confirm the details are correct and agree to be contacted about jobs.", send: "Submit application",
         sending: "Sending…", ok: "Thank you! Your application has been received.", ref: "Reference",
         again: "Send another application", required: "Please fill in the required fields.", fail: "Could not send. Please try again or contact us on WhatsApp.",
         choose: "Choose…", freeNote: "We never charge job seekers to apply."},
    ar: {title: "طلب توظيف", personal: "البيانات الشخصية", contact: "التواصل", passport: "جواز السفر", work: "الوظيفة والخبرة",
         docs: "السيرة الذاتية", name: "الاسم الكامل (كما في الجواز)", gender: "الجنس", male: "ذكر", female: "أنثى",
         dob: "تاريخ الميلاد", nationality: "الجنسية", marital: "الحالة الاجتماعية", single: "أعزب", married: "متزوج",
         phone: "رقم الجوال / واتساب", email: "البريد الإلكتروني", location: "مكان الإقامة الحالي",
         ppno: "رقم الجواز", ppexp: "تاريخ انتهاء الجواز", position: "الوظيفة المطلوبة", any: "أي وظيفة مناسبة",
         other: "أخرى (اكتبها أدناه)", trade: "مهنتك / مهارتك", exp: "سنوات الخبرة", gulf: "خبرة خليجية؟",
         yes: "نعم", no: "لا", edu: "أعلى مؤهل", langs: "اللغات", licence: "رخصة القيادة",
         none: "لا يوجد", indian: "من بلدي", gcc: "رخصة خليجية", salary: "الراتب المتوقع (شهرياً)",
         notice: "متى يمكنك الالتحاق؟", now: "فوراً", m1: "خلال شهر", m2: "١–٣ أشهر",
         cv: "السيرة الذاتية (PDF أو Word أو صورة، حتى 8MB)", msg: "ملاحظات إضافية (اختياري)",
         consent: "أؤكد صحة البيانات وأوافق على التواصل معي بخصوص الوظائف.", send: "إرسال الطلب",
         sending: "جارٍ الإرسال…", ok: "شكراً لك! تم استلام طلبك.", ref: "الرقم المرجعي",
         again: "إرسال طلب آخر", required: "يرجى تعبئة الحقول المطلوبة.", fail: "تعذر الإرسال. حاول مرة أخرى أو تواصل معنا عبر واتساب.",
         choose: "اختر…", freeNote: "لا نتقاضى أي رسوم من المتقدمين."}
  };
  var CSS = ".bpf{--c:#0f766e;font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,'Noto Sans Arabic',sans-serif;color:#0f172a;max-width:760px;margin:0 auto;text-align:start}" +
    ".bpf *{box-sizing:border-box}.bpf h3{font-size:22px;margin:0 0 4px}.bpf .bpf-note{color:#64748b;font-size:13px;margin:0 0 14px}" +
    ".bpf fieldset{border:1px solid #e2e8f0;border-radius:14px;padding:14px 16px 6px;margin:0 0 14px;background:#fff}" +
    ".bpf legend{font-weight:700;padding:0 6px;color:var(--c)}.bpf .g{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px}" +
    ".bpf .f{margin-bottom:10px}.bpf .w{grid-column:1/-1}.bpf label{display:block;font-size:13px;font-weight:600;color:#334155;margin-bottom:4px}" +
    ".bpf input,.bpf select,.bpf textarea{width:100%;padding:11px 12px;border:1.5px solid #cbd5e1;border-radius:10px;font:inherit;background:#fff;color:#0f172a}" +
    ".bpf input:focus,.bpf select:focus,.bpf textarea:focus{outline:none;border-color:var(--c);box-shadow:0 0 0 3px color-mix(in srgb,var(--c) 18%,transparent)}" +
    ".bpf .req{color:#dc2626}.bpf .chk{display:flex;gap:9px;align-items:flex-start;font-weight:500}.bpf .chk input{width:18px;height:18px;margin-top:2px;flex:none}" +
    ".bpf button{width:100%;padding:14px;border:0;border-radius:12px;background:var(--c);color:#fff;font:inherit;font-weight:700;font-size:16px;cursor:pointer}" +
    ".bpf button[disabled]{opacity:.6}.bpf .err{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;border-radius:10px;padding:10px 12px;margin-bottom:12px;font-weight:600}" +
    ".bpf .done{text-align:center;padding:30px 16px;border:1px solid #e2e8f0;border-radius:14px;background:#fff}.bpf .done b{display:block;font-size:20px;margin:8px 0}" +
    ".bpf .hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}" +
    "@media(max-width:600px){.bpf .g{grid-template-columns:1fr}}";

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }

  function render(box) {
    var asked = (box.getAttribute("data-lang") || "").toLowerCase(), server = CFG.t && (!asked || asked === CFG.lang);
    var lang = server ? CFG.lang : (asked || document.documentElement.lang || "en").slice(0, 2).toLowerCase();
    var t = server ? CFG.t : (T[lang] || T.en);
    if (server ? CFG.rtl : lang === "ar") box.setAttribute("dir", "rtl");
    box.classList.add("bpf");
    box.style.setProperty("--c", box.getAttribute("data-color") || CFG.color);
    var opt = function (v, l) { return '<option value="' + esc(v) + '">' + esc(l) + "</option>"; };
    var field = function (name, label, input, cls, req) {
      return '<div class="f ' + (cls || "") + '"><label for="bpf-' + name + '">' + esc(label) + (req ? ' <span class="req">*</span>' : "") + "</label>" + input + "</div>";
    };
    var inp = function (name, type, req, extra) {
      return '<input id="bpf-' + name + '" name="' + name + '" type="' + (type || "text") + '"' + (req ? " required" : "") + (extra || "") + ">";
    };
    var sel = function (name, opts, req) { return '<select id="bpf-' + name + '" name="' + name + '"' + (req ? " required" : "") + ">" + opts + "</select>"; };
    var ppReq = !!CFG.ask_passport;
    box.innerHTML =
      "<h3>" + esc(box.getAttribute("data-title") || t.title) + "</h3><p class=\"bpf-note\">" + esc(CFG.company) + " · " + esc(t.freeNote) + "</p>" +
      '<form novalidate><div class="err" hidden></div><div class="hp" aria-hidden="true"><input name="company_website" tabindex="-1" autocomplete="off"></div>' +
      "<fieldset><legend>" + esc(t.work) + '</legend><div class="g">' +
        field("job", t.position, sel("job", opt("", t.any)), "w") +
        field("trade", t.trade, inp("trade", "text", true, ' maxlength="150"'), "", true) +
        field("experience_years", t.exp, inp("experience_years", "number", false, ' min="0" max="60" step="0.5"')) +
        field("gulf_experience", t.gulf, sel("gulf_experience", opt("", t.choose) + opt("yes", t.yes) + opt("no", t.no))) +
        field("expected_salary", t.salary, inp("expected_salary", "number", false, ' min="0" step="50"')) +
        field("education", t.edu, inp("education", "text", false, ' maxlength="150"')) +
        field("languages", t.langs, inp("languages", "text", false, ' maxlength="150" placeholder="English, Arabic, Hindi"')) +
        field("driving_licence", t.licence, sel("driving_licence", opt("", t.choose) + opt("None", t.none) + opt("Home country", t.indian) + opt("GCC", t.gcc))) +
        field("notice_period", t.notice, sel("notice_period", opt("", t.choose) + opt("Immediately", t.now) + opt("Within 1 month", t.m1) + opt("1-3 months", t.m2))) +
      "</div></fieldset>" +
      "<fieldset><legend>" + esc(t.personal) + '</legend><div class="g">' +
        field("name", t.name, inp("name", "text", true, ' maxlength="150" autocomplete="name"'), "w", true) +
        field("gender", t.gender, sel("gender", opt("", t.choose) + opt("male", t.male) + opt("female", t.female))) +
        field("date_of_birth", t.dob, inp("date_of_birth", "date")) +
        field("nationality", t.nationality, inp("nationality", "text", true, ' maxlength="100"'), "", true) +
        field("marital_status", t.marital, sel("marital_status", opt("", t.choose) + opt("Single", t.single) + opt("Married", t.married))) +
      "</div></fieldset>" +
      "<fieldset><legend>" + esc(t.contact) + '</legend><div class="g">' +
        field("phone", t.phone, inp("phone", "tel", true, ' maxlength="30" autocomplete="tel" placeholder="+91 98765 43210"'), "", true) +
        field("email", t.email, inp("email", "email", false, ' maxlength="254" autocomplete="email"')) +
        field("current_location", t.location, inp("current_location", "text", false, ' maxlength="150"'), "w") +
      "</div></fieldset>" +
      "<fieldset><legend>" + esc(t.passport) + '</legend><div class="g">' +
        field("passport_no", t.ppno, inp("passport_no", "text", ppReq, ' maxlength="30" style="text-transform:uppercase"'), "", ppReq) +
        field("passport_expiry", t.ppexp, inp("passport_expiry", "date")) +
      "</div></fieldset>" +
      "<fieldset><legend>" + esc(t.docs) + '</legend><div class="g">' +
        field("cv", t.cv, '<input id="bpf-cv" name="cv" type="file" accept=".pdf,.doc,.docx,image/*">', "w") +
        field("message", t.msg, '<textarea id="bpf-message" name="message" rows="3" maxlength="2000"></textarea>', "w") +
        '<div class="f w"><label class="chk"><input type="checkbox" name="consent" required> <span>' + esc(t.consent) + "</span></label></div>" +
      "</div></fieldset>" +
      '<button type="submit">' + esc(t.send) + "</button></form>";

    var form = box.querySelector("form"), err = box.querySelector(".err"), jobSel = box.querySelector("#bpf-job");
    var wanted = box.getAttribute("data-job") || "";
    fetch(CFG.jobs).then(function (r) { return r.json(); }).then(function (d) {
      (d.jobs || []).forEach(function (j) {
        var o = document.createElement("option");
        o.value = j.id; o.textContent = j.position + (j.location ? " — " + j.location : "");
        if (String(j.id) === wanted || j.position.toLowerCase() === wanted.toLowerCase()) o.selected = true;
        jobSel.appendChild(o);
      });
      var other = document.createElement("option"); other.value = ""; other.textContent = t.other; jobSel.appendChild(other);
      jobSel.dispatchEvent(new Event("change"));
    }).catch(function () {});
    jobSel.addEventListener("change", function () {
      var o = jobSel.options[jobSel.selectedIndex], trade = box.querySelector("#bpf-trade");
      if (jobSel.value && !trade.value) trade.value = o.textContent.split(" — ")[0];
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      err.hidden = true;
      if (!form.checkValidity()) { err.textContent = t.required; err.hidden = false; form.reportValidity && form.reportValidity(); return; }
      var btn = form.querySelector("button"); btn.disabled = true; btn.textContent = t.sending;
      var data = new FormData(form);
      data.delete("consent");
      fetch(CFG.endpoint, {method: "POST", body: data, mode: "cors", credentials: "omit", headers: {"Accept": "application/json"}})
        .then(function (r) { return r.json().catch(function () { return {ok: false}; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.error || t.fail);
          var thanks = box.getAttribute("data-thanks");
          if (thanks) { window.location.href = thanks; return; }
          box.innerHTML = '<div class="done"><div style="font-size:40px">✅</div><b>' + esc(t.ok) + "</b>" + (res.reference ? esc(t.ref) + ": <strong>" + esc(res.reference) + "</strong>" : "") +
            '<p><a href="#" class="bpf-again">' + esc(t.again) + "</a></p></div>";
          box.querySelector(".bpf-again").addEventListener("click", function (ev) { ev.preventDefault(); render(box); });
          box.scrollIntoView({behavior: "smooth", block: "start"});
        })
        .catch(function (ex) {
          err.textContent = ex && ex.message && ex.message !== "Failed to fetch" ? ex.message : t.fail;
          err.hidden = false; btn.disabled = false; btn.textContent = t.send;
          err.scrollIntoView({behavior: "smooth", block: "center"});
        });
    });
  }

  function start() {
    if (!document.getElementById("bpf-style")) {
      var st = document.createElement("style"); st.id = "bpf-style"; st.textContent = CSS; document.head.appendChild(st);
    }
    var boxes = document.querySelectorAll(".bookpilot-form, #bookpilot-form");
    for (var i = 0; i < boxes.length; i++) if (!boxes[i].getAttribute("data-ready")) { boxes[i].setAttribute("data-ready", "1"); render(boxes[i]); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
