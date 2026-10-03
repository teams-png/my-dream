/* BookPilot online booking form — works on any website (WordPress "Custom HTML" block, Elementor "HTML" widget).
   <div class="bookpilot-booking"></div>
   <script src="…/book/<name>/form.js" defer></script>
   Optional attributes on the <div>: data-lang="en|ar", data-item="<service / room id or name>", data-color="#0f766e",
   data-thanks="https://your-site/thank-you", data-title="Book now" */
(function () {
  "use strict";
  var CFG = {{ cfg|safe }};
  var T = {
    en: {appointment: "Book an appointment", resource: "Book now", table: "Reserve a table", event: "Event enquiry",
         any: "Not sure / other", date: "Date", time: "Time", guests: "Number of people", partySize: "Number of guests",
         name: "Your name", phone: "Mobile / WhatsApp number", email: "Email (optional)", notes: "Notes (optional)",
         eventType: "Type of event", eventPh: "Wedding, birthday, corporate…", send: "Send booking request", sending: "Sending…",
         ok: "Thank you! We received your request.", okNote: "We will confirm on WhatsApp or by phone shortly.",
         ref: "Reference", again: "Make another booking", fail: "Could not send. Please try again or contact us on WhatsApp.",
         required: "Please fill in the required fields.", per: {hour: "/ hour", day: "/ day", night: "/ night", month: "/ month", event: ""},
         mins: "min", choose: "Choose…", endTime: "Until (time)"},
    ar: {appointment: "احجز موعداً", resource: "احجز الآن", table: "احجز طاولة", event: "استفسار عن مناسبة",
         any: "غير متأكد / أخرى", date: "التاريخ", time: "الوقت", guests: "عدد الأشخاص", partySize: "عدد الضيوف",
         name: "الاسم", phone: "رقم الجوال / واتساب", email: "البريد الإلكتروني (اختياري)", notes: "ملاحظات (اختياري)",
         eventType: "نوع المناسبة", eventPh: "زفاف، عيد ميلاد، شركة…", send: "إرسال طلب الحجز", sending: "جارٍ الإرسال…",
         ok: "شكراً لك! تم استلام طلبك.", okNote: "سنؤكد الحجز عبر واتساب أو الهاتف قريباً.",
         ref: "الرقم المرجعي", again: "حجز آخر", fail: "تعذر الإرسال. حاول مرة أخرى أو تواصل معنا عبر واتساب.",
         required: "يرجى تعبئة الحقول المطلوبة.", per: {hour: "/ ساعة", day: "/ يوم", night: "/ ليلة", month: "/ شهر", event: ""},
         mins: "دقيقة", choose: "اختر…", endTime: "حتى (الوقت)"}
  };
  var AR_LABELS = {"Service": "الخدمة", "Room": "الغرفة", "Vehicle": "السيارة", "Equipment": "المعدات", "Hall": "القاعة",
    "Space": "المساحة", "Check-in": "الوصول", "Check-out": "المغادرة", "Pick-up": "الاستلام", "Return": "الإرجاع",
    "From": "من", "Until": "إلى", "Event date": "تاريخ المناسبة", "Ends": "ينتهي", "Date": "التاريخ",
    "Membership / trial": "الاشتراك / تجربة", "Wash package": "باقة الغسيل", "Item": "العنصر"};
  var CSS = ".bpb{--c:#0f766e;font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,'Noto Sans Arabic',sans-serif;color:#0f172a;max-width:640px;margin:0 auto;text-align:start}" +
    ".bpb *{box-sizing:border-box}.bpb h3{font-size:22px;margin:0 0 4px}.bpb .sub{color:#64748b;font-size:13.5px;margin:0 0 14px}" +
    ".bpb form{border:1px solid #e2e8f0;border-radius:16px;padding:18px;background:#fff}.bpb .g{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px}" +
    ".bpb .f{margin-bottom:12px}.bpb .w{grid-column:1/-1}.bpb label{display:block;font-size:13px;font-weight:600;color:#334155;margin-bottom:4px}" +
    ".bpb input,.bpb select,.bpb textarea{width:100%;padding:11px 12px;border:1.5px solid #cbd5e1;border-radius:10px;font:inherit;background:#fff;color:#0f172a}" +
    ".bpb input:focus,.bpb select:focus,.bpb textarea:focus{outline:none;border-color:var(--c)}.bpb .req{color:#dc2626}" +
    ".bpb .items{display:grid;gap:8px}.bpb .it{display:flex;gap:10px;align-items:center;border:1.5px solid #e2e8f0;border-radius:12px;padding:10px 12px;cursor:pointer;font-weight:600}" +
    ".bpb .it input{width:18px;height:18px;flex:none;accent-color:var(--c)}.bpb .it small{display:block;color:#64748b;font-weight:500}.bpb .it .p{margin-inline-start:auto;white-space:nowrap;color:var(--c)}" +
    ".bpb .it:has(input:checked){border-color:var(--c);background:color-mix(in srgb,var(--c) 7%,#fff)}" +
    ".bpb button{width:100%;padding:14px;border:0;border-radius:12px;background:var(--c);color:#fff;font:inherit;font-weight:700;font-size:16px;cursor:pointer}" +
    ".bpb button[disabled]{opacity:.6}.bpb .err{background:#fef2f2;color:#991b1b;border:1px solid #fecaca;border-radius:10px;padding:10px 12px;margin-bottom:12px;font-weight:600}" +
    ".bpb .done{text-align:center;padding:30px 16px;border:1px solid #e2e8f0;border-radius:16px;background:#fff}.bpb .done b{display:block;font-size:20px;margin:8px 0}" +
    ".bpb .hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}@media(max-width:560px){.bpb .g{grid-template-columns:1fr}}";

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }

  function render(box) {
    var lang = (box.getAttribute("data-lang") || document.documentElement.lang || "en").slice(0, 2).toLowerCase();
    var t = T[lang] || T.en, kind = CFG.kind, L = CFG.labels || {};
    var lab = function (k) { var v = L[k] || k; return lang === "ar" && AR_LABELS[v] ? AR_LABELS[v] : v; };
    if (lang === "ar") box.setAttribute("dir", "rtl");
    box.classList.add("bpb");
    box.style.setProperty("--c", box.getAttribute("data-color") || CFG.color);
    var f = function (name, label, input, cls, req) {
      return '<div class="f ' + (cls || "") + '"><label for="bpb-' + name + '">' + esc(label) + (req ? ' <span class="req">*</span>' : "") + "</label>" + input + "</div>";
    };
    var inp = function (name, type, req, extra) { return '<input id="bpb-' + name + '" name="' + name + '" type="' + type + '"' + (req ? " required" : "") + (extra || "") + ">"; };
    var wanted = (box.getAttribute("data-item") || "").toLowerCase();
    var items = CFG.items || [], html = "";
    if ((kind === "appointment" || kind === "resource") && items.length) {
      html += '<div class="f w"><label>' + esc(lab("item")) + ' <span class="req">*</span></label><div class="items">';
      items.forEach(function (it, i) {
        var price = it.price ? CFG.currency + " " + it.price + " " + (it.unit ? t.per[it.unit] || "" : "") : "";
        var sub = [it.minutes ? it.minutes + " " + t.mins : "", it.details || ""].filter(Boolean).join(" · ");
        var on = wanted ? (String(it.id) === wanted || it.name.toLowerCase() === wanted) : (items.length === 1);
        html += '<label class="it"><input type="radio" name="item" value="' + it.id + '" data-unit="' + esc(it.unit || "") + '"' + (on ? " checked" : "") + ' required><span>' + esc(it.name) +
          (sub ? "<small>" + esc(sub) + "</small>" : "") + '</span><span class="p">' + esc(price) + "</span></label>";
      });
      if (kind === "appointment") html += '<label class="it"><input type="radio" name="item" value=""><span>' + esc(t.any) + "</span></label>";
      html += "</div></div>";
    } else if (kind === "event") {
      html += f("item_name", t.eventType, inp("item_name", "text", false, ' maxlength="150" placeholder="' + esc(t.eventPh) + '"'), "w");
    } else if (kind === "appointment") {
      html += f("item_name", lab("item"), inp("item_name", "text", false, ' maxlength="150"'), "w");
    }
    var dates = '<div class="g">' + f("date", kind === "resource" ? lab("start") : t.date,
      inp("date", "date", true, ' min="' + CFG.min_date + '" max="' + CFG.max_date + '"'), "", true);
    var timeReq = kind === "appointment" || kind === "table";
    dates += '<div class="f bpb-time"><label for="bpb-time">' + esc(t.time) + (timeReq ? ' <span class="req">*</span>' : "") + "</label>" + inp("time", "time", timeReq, ' step="900"') + "</div>";
    if (kind === "resource") {
      dates += '<div class="f bpb-end"><label for="bpb-end_date">' + esc(lab("end")) + "</label>" + inp("end_date", "date", false, ' min="' + CFG.min_date + '"') + "</div>";
      dates += '<div class="f bpb-endtime"><label for="bpb-end_time">' + esc(t.endTime) + "</label>" + inp("end_time", "time", false, ' step="900"') + "</div>";
    }
    if (kind !== "appointment") dates += f("guests", kind === "table" ? t.partySize : t.guests, inp("guests", "number", true, ' min="1" max="5000" value="' + (kind === "table" ? 2 : 1) + '"'), "", true);
    dates += "</div>";
    html += dates + '<div class="g">' +
      f("name", t.name, inp("name", "text", true, ' maxlength="150" autocomplete="name"'), "", true) +
      f("phone", t.phone, inp("phone", "tel", true, ' maxlength="30" autocomplete="tel"'), "", true) +
      f("email", t.email, inp("email", "email", false, ' maxlength="254" autocomplete="email"'), "w") +
      f("notes", t.notes, '<textarea id="bpb-notes" name="notes" rows="3" maxlength="2000"></textarea>', "w") + "</div>";
    box.innerHTML = "<h3>" + esc(box.getAttribute("data-title") || CFG.headline || t[kind]) + '</h3><p class="sub">' + esc(CFG.company) + (CFG.note ? " · " + esc(CFG.note) : "") + "</p>" +
      '<form novalidate><div class="err" hidden></div><div class="hp" aria-hidden="true"><input name="company_website" tabindex="-1" autocomplete="off"></div>' + html +
      '<button type="submit">' + esc(t.send) + "</button></form>";

    var form = box.querySelector("form"), err = box.querySelector(".err");
    function syncUnit() {
      if (kind !== "resource") return;
      var picked = form.querySelector("input[name=item]:checked"), unit = picked ? picked.getAttribute("data-unit") : "day";
      var hourly = unit === "hour" || unit === "event";
      form.querySelector(".bpb-end").style.display = hourly ? "none" : "";
      form.querySelector(".bpb-endtime").style.display = hourly ? "" : "none";
      form.querySelector(".bpb-time").style.display = unit === "night" ? "none" : "";
    }
    form.addEventListener("change", syncUnit); syncUnit();
    form.addEventListener("submit", function (e) {
      e.preventDefault(); err.hidden = true;
      if (!form.checkValidity()) { err.textContent = t.required; err.hidden = false; form.reportValidity && form.reportValidity(); return; }
      var btn = form.querySelector("button"); btn.disabled = true; btn.textContent = t.sending;
      fetch(CFG.endpoint, {method: "POST", body: new FormData(form), mode: "cors", credentials: "omit", headers: {"Accept": "application/json"}})
        .then(function (r) { return r.json().catch(function () { return {ok: false}; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.error || t.fail);
          var thanks = box.getAttribute("data-thanks");
          if (thanks) { window.location.href = thanks; return; }
          box.innerHTML = '<div class="done"><div style="font-size:40px">✅</div><b>' + esc(t.ok) + "</b><p>" + esc(t.okNote) + "</p>" +
            (res.reference ? esc(t.ref) + ": <strong>" + esc(res.reference) + "</strong>" : "") +
            (CFG.whatsapp ? '<p><a href="https://wa.me/' + esc(CFG.whatsapp) + '" target="_blank" rel="noopener">WhatsApp</a></p>' : "") +
            '<p><a href="#" class="bpb-again">' + esc(t.again) + "</a></p></div>";
          box.querySelector(".bpb-again").addEventListener("click", function (ev) { ev.preventDefault(); render(box); });
          box.scrollIntoView({behavior: "smooth", block: "start"});
        })
        .catch(function (ex) {
          err.textContent = ex && ex.message && ex.message !== "Failed to fetch" ? ex.message : t.fail;
          err.hidden = false; btn.disabled = false; btn.textContent = t.send;
        });
    });
  }

  function start() {
    if (!document.getElementById("bpb-style")) { var st = document.createElement("style"); st.id = "bpb-style"; st.textContent = CSS; document.head.appendChild(st); }
    var boxes = document.querySelectorAll(".bookpilot-booking, #bookpilot-booking");
    for (var i = 0; i < boxes.length; i++) if (!boxes[i].getAttribute("data-ready")) { boxes[i].setAttribute("data-ready", "1"); render(boxes[i]); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
