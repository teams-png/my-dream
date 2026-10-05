/* BookPilot contact / enquiry form — <div class="bookpilot-enquiry"></div> + this script.
   Optional: data-lang="en|ar|…" (or ?lang= on the script URL for any BookPilot language), data-title, data-thanks="https://…", data-color="#…" */
(function () {
  "use strict";
  var CFG = {{ cfg|safe }};
  var T = {en: {title: "Send us a message", name: "Your name", phone: "Phone / WhatsApp", email: "Email", subject: "Subject",
                message: "Message", send: "Send", sending: "Sending…", ok: "Thank you! We will get back to you soon.",
                fail: "Could not send. Please try again.", req: "Please enter your name and a phone number or email."},
           ar: {title: "راسلنا", name: "الاسم", phone: "الهاتف / واتساب", email: "البريد الإلكتروني", subject: "الموضوع",
                message: "الرسالة", send: "إرسال", sending: "جارٍ الإرسال…", ok: "شكراً لك! سنتواصل معك قريباً.",
                fail: "تعذر الإرسال. حاول مرة أخرى.", req: "يرجى إدخال الاسم ورقم الهاتف أو البريد."}};
  var CSS = ".bpe{--c:#0f766e;font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,'Noto Sans Arabic',sans-serif;color:#0f172a;max-width:560px;margin:0 auto;text-align:start}" +
    ".bpe *{box-sizing:border-box}.bpe h3{margin:0 0 12px;font-size:21px}.bpe form{border:1px solid #e2e8f0;border-radius:16px;padding:18px;background:#fff}" +
    ".bpe .g{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px}.bpe .f{margin-bottom:11px}.bpe .w{grid-column:1/-1}" +
    ".bpe label{display:block;font-size:13px;font-weight:600;color:#334155;margin-bottom:4px}" +
    ".bpe input,.bpe textarea{width:100%;padding:11px 12px;border:1.5px solid #cbd5e1;border-radius:10px;font:inherit;background:#fff;color:#0f172a}" +
    ".bpe input:focus,.bpe textarea:focus{outline:none;border-color:var(--c)}" +
    ".bpe button{width:100%;padding:13px;border:0;border-radius:12px;background:var(--c);color:#fff;font:inherit;font-weight:700;font-size:16px;cursor:pointer}" +
    ".bpe .msg{border-radius:10px;padding:10px 12px;margin-bottom:12px;font-weight:600}.bpe .bad{background:#fef2f2;color:#991b1b}.bpe .good{background:#ecfdf5;color:#065f46}" +
    ".bpe .hp{position:absolute;left:-9999px}@media(max-width:520px){.bpe .g{grid-template-columns:1fr}}";
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function render(box) {
    var asked = (box.getAttribute("data-lang") || "").toLowerCase(),
        lang = (asked || CFG.lang || document.documentElement.lang || "en").toLowerCase(),
        t = (CFG.t && (!asked || asked === CFG.lang)) ? CFG.t : (T[lang.slice(0, 2)] || CFG.t || T.en);
    if (t === CFG.t ? CFG.rtl : lang.slice(0, 2) === "ar") box.setAttribute("dir", "rtl");
    box.classList.add("bpe"); box.style.setProperty("--c", box.getAttribute("data-color") || CFG.color);
    var f = function (n, l, i, w) { return '<div class="f' + (w ? " w" : "") + '"><label for="bpe-' + n + '">' + esc(l) + "</label>" + i + "</div>"; };
    box.innerHTML = "<h3>" + esc(box.getAttribute("data-title") || t.title) + '</h3><form novalidate><div class="msg bad" hidden></div>' +
      '<div class="hp" aria-hidden="true"><input name="company_website" tabindex="-1" autocomplete="off"></div><div class="g">' +
      f("name", t.name + " *", '<input id="bpe-name" name="name" maxlength="150" required autocomplete="name">', true) +
      f("phone", t.phone, '<input id="bpe-phone" name="phone" type="tel" maxlength="30" autocomplete="tel">') +
      f("email", t.email, '<input id="bpe-email" name="email" type="email" maxlength="254" autocomplete="email">') +
      f("subject", t.subject, '<input id="bpe-subject" name="subject" maxlength="150">', true) +
      f("message", t.message, '<textarea id="bpe-message" name="message" rows="4" maxlength="4000"></textarea>', true) +
      '</div><button type="submit">' + esc(t.send) + "</button></form>";
    var form = box.querySelector("form"), err = box.querySelector(".msg");
    form.addEventListener("submit", function (e) {
      e.preventDefault(); err.hidden = true;
      var v = function (n) { return form.querySelector("[name=" + n + "]").value.trim(); };
      if (!v("name") || !(v("phone") || v("email"))) { err.textContent = t.req; err.hidden = false; return; }
      var b = form.querySelector("button"); b.disabled = true; b.textContent = t.sending;
      fetch(CFG.endpoint, {method: "POST", body: new FormData(form), mode: "cors", credentials: "omit", headers: {"Accept": "application/json"}})
        .then(function (r) { return r.json().catch(function () { return {ok: false}; }); })
        .then(function (res) {
          if (!res.ok) throw new Error(res.error || t.fail);
          var thanks = box.getAttribute("data-thanks"); if (thanks) { location.href = thanks; return; }
          form.innerHTML = '<div class="msg good">' + esc(t.ok) + "</div>";
        })
        .catch(function (ex) { err.textContent = ex && ex.message && ex.message !== "Failed to fetch" ? ex.message : t.fail; err.hidden = false; b.disabled = false; b.textContent = t.send; });
    });
  }
  function start() {
    if (!document.getElementById("bpe-style")) { var st = document.createElement("style"); st.id = "bpe-style"; st.textContent = CSS; document.head.appendChild(st); }
    document.querySelectorAll(".bookpilot-enquiry").forEach(function (b) { if (!b.getAttribute("data-ready")) { b.setAttribute("data-ready", "1"); render(b); } });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
