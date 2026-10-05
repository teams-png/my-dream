/* BookPilot website ordering: "+ Add" buttons, a cart and checkout. Orders go to the restaurant's BookPilot. */
(function () {
  "use strict";
  var cfg = {{ cfg|safe }};
  if (window.__bpOrder || !cfg.enabled) return;
  window.__bpOrder = true;
  var L = cfg.t || {}, cur = cfg.currency || "", color = cfg.color || "#0f766e", cart = load();

  function load() { try { var c = JSON.parse(localStorage.getItem(cfg.key) || "[]"); return Array.isArray(c) ? c : []; } catch (e) { return []; } }
  function save() { try { localStorage.setItem(cfg.key, JSON.stringify(cart)); } catch (e) {} }
  function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function money(n) { return cur + " " + (Math.round(n * 100) / 100).toFixed(2); }
  function count() { return cart.reduce(function (s, x) { return s + x.qty; }, 0); }
  function subtotal() { return cart.reduce(function (s, x) { return s + x.qty * x.price; }, 0); }
  function find(id) { for (var i = 0; i < cart.length; i++) if (cart[i].id === id) return cart[i]; return null; }

  var css = ".bpo-bar{position:fixed;left:50%;transform:translateX(-50%);bottom:16px;z-index:99998;display:none;align-items:center;gap:12px;" +
    "padding:13px 20px;border-radius:999px;background:" + color + ";color:#fff;font:600 15px/1.2 system-ui,sans-serif;border:0;cursor:pointer;" +
    "box-shadow:0 10px 30px rgba(0,0,0,.28);max-width:calc(100vw - 32px);white-space:nowrap}.bpo-bar.on{display:flex}" +
    "@media(max-width:560px){.bpo-bar{left:16px;transform:none;max-width:calc(100vw - 100px);padding:12px 16px;font-size:14px}}.bpo-bar b{background:#fff;color:" + color +
    ";border-radius:99px;min-width:24px;height:24px;display:grid;place-items:center;font-size:13px;padding:0 6px}" +
    ".bpo-bg{position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:99999;display:none}.bpo-bg.on{display:block}" +
    ".bpo-box{position:fixed;z-index:100000;right:0;top:0;bottom:0;width:min(440px,100vw);background:#fff;color:#172033;display:none;flex-direction:column;" +
    "font:15px/1.45 system-ui,sans-serif;box-shadow:-10px 0 40px rgba(0,0,0,.2)}.bpo-box.on{display:flex}" +
    ".bpo-box *{box-sizing:border-box}.bpo-head{display:flex;align-items:center;gap:10px;padding:16px 18px;border-bottom:1px solid #e5e7eb}" +
    ".bpo-head h3{margin:0;flex:1;font-size:19px}.bpo-x{border:0;background:#f1f5f9;border-radius:50%;width:36px;height:36px;font-size:18px;cursor:pointer}" +
    ".bpo-body{flex:1;overflow:auto;padding:14px 18px}.bpo-line{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f1f5f9}" +
    ".bpo-line .n{flex:1;min-width:0}.bpo-line .n small{display:block;color:#64748b}.bpo-q{display:flex;align-items:center;gap:6px}" +
    ".bpo-q button{width:32px;height:32px;border-radius:50%;border:1px solid #cbd5e1;background:#fff;font-size:17px;cursor:pointer;color:#172033}" +
    ".bpo-q span{min-width:20px;text-align:center;font-weight:700}.bpo-sum{margin:12px 0;display:grid;gap:4px}.bpo-sum div{display:flex;justify-content:space-between}" +
    ".bpo-sum .t{font-weight:800;font-size:18px}.bpo-modes{display:flex;gap:8px;margin:6px 0 12px}.bpo-modes label{flex:1;border:1.5px solid #cbd5e1;border-radius:12px;" +
    "padding:10px;text-align:center;font-weight:700;cursor:pointer}.bpo-modes input{display:none}.bpo-modes label.on{border-color:" + color + ";background:" + color + "14;color:" + color + "}" +
    ".bpo-f{display:grid;gap:10px}.bpo-f input,.bpo-f textarea{width:100%;padding:11px 12px;border:1.5px solid #cbd5e1;border-radius:10px;font:inherit;color:#172033;background:#fff}" +
    ".bpo-f input:focus,.bpo-f textarea:focus{outline:2px solid " + color + "55;border-color:" + color + "}.bpo-hp{position:absolute;left:-9999px}" +
    ".bpo-foot{padding:14px 18px;border-top:1px solid #e5e7eb}.bpo-go{width:100%;padding:14px;border:0;border-radius:12px;background:" + color +
    ";color:#fff;font:700 16px system-ui,sans-serif;cursor:pointer}.bpo-go[disabled]{opacity:.6;cursor:wait}" +
    ".bpo-err{color:#b91c1c;font-weight:600;margin:8px 0 0}.bpo-note{background:#fef9c3;color:#713f12;border-radius:10px;padding:8px 12px;margin:0 0 12px;font-size:14px}" +
    ".bpo-done{text-align:center;padding:30px 10px}.bpo-done .big{font-size:52px}.bpo-done a{color:" + color + ";font-weight:700}" +
    ".bpo-toast{position:fixed;left:50%;transform:translateX(-50%);bottom:84px;z-index:100001;background:#172033;color:#fff;padding:10px 16px;border-radius:12px;" +
    "font:600 14px system-ui,sans-serif;opacity:0;transition:opacity .2s;pointer-events:none;max-width:calc(100vw - 32px)}.bpo-toast.on{opacity:1}" +
    "[data-bp-add].bpo-in{background:" + color + "!important;color:#fff!important;border-color:" + color + "!important}";
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  var bar = document.createElement("button"); bar.type = "button"; bar.className = "bpo-bar";
  var bg = document.createElement("div"); bg.className = "bpo-bg";
  var box = document.createElement("div"); box.className = "bpo-box"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", L.your_order);
  if (cfg.rtl) box.setAttribute("dir", "rtl");
  var toast = document.createElement("div"); toast.className = "bpo-toast";
  document.body.appendChild(bar); document.body.appendChild(bg); document.body.appendChild(box); document.body.appendChild(toast);
  var mode = cfg.pickup ? "pickup" : "delivery", form = {name: "", phone: "", address: "", note: ""}, sending = false, done = null;

  function say(text) { toast.textContent = text; toast.classList.add("on"); clearTimeout(say.t); say.t = setTimeout(function () { toast.classList.remove("on"); }, 2200); }

  function paintButtons() {
    var els = document.querySelectorAll("[data-bp-add]");
    for (var i = 0; i < els.length; i++) {
      var b = els[i], line = find(+b.getAttribute("data-id"));
      if (!b.getAttribute("data-label")) b.setAttribute("data-label", b.textContent);
      b.textContent = line ? "✓ " + line.qty + " · +" : b.getAttribute("data-label");
      b.classList.toggle("bpo-in", !!line);
    }
    var n = count();
    bar.innerHTML = "🛒 <b>" + n + "</b> <span>" + esc(money(subtotal())) + "</span> <span>· " + esc(L.view_order) + "</span>";
    bar.classList.toggle("on", n > 0 && !box.classList.contains("on"));
  }

  function fee() { return mode === "delivery" ? parseFloat(cfg.delivery_fee || 0) : 0; }

  function render() {
    if (done) {
      box.innerHTML = '<div class="bpo-head"><h3>' + esc(L.order_sent) + '</h3><button class="bpo-x" type="button" data-close>✕</button></div><div class="bpo-body"><div class="bpo-done">' +
        '<div class="big">✅</div><h2 style="margin:6px 0">' + esc(done.reference) + "</h2><p>" + esc(L.thanks) + " " +
        esc(done.accepted ? L.in_kitchen : L.will_confirm) +
        (cfg.ready_minutes ? " " + esc(L.ready_in.replace("%s", cfg.ready_minutes)) : "") + "</p><p>" + esc(L.total) + " " + esc(money(+done.total)) +
        " — " + esc(mode === "delivery" ? L.pay_delivery : L.pay_pickup) + '</p><p><a href="' + esc(done.track_url) + '" target="_blank" rel="noopener">' + esc(L.track) + " →</a></p></div></div>";
      return;
    }
    var rows = cart.map(function (x) {
      return '<div class="bpo-line"><div class="n">' + esc(x.name) + "<small>" + esc(money(x.price)) + '</small></div><div class="bpo-q">' +
        '<button type="button" data-dec="' + x.id + '" aria-label="−">−</button><span>' + x.qty + '</span><button type="button" data-inc="' + x.id + '" aria-label="+">+</button></div>' +
        '<div style="min-width:76px;text-align:end;font-weight:700">' + esc(money(x.qty * x.price)) + "</div></div>";
    }).join("") || '<p style="color:#64748b">' + esc(L.empty) + "</p>";
    var modes = "";
    if (cfg.pickup && cfg.delivery) {
      modes = '<div class="bpo-modes"><label class="' + (mode === "pickup" ? "on" : "") + '"><input type="radio" name="bpo-mode" value="pickup">🛍 ' + esc(L.pickup) + "</label>" +
        '<label class="' + (mode === "delivery" ? "on" : "") + '"><input type="radio" name="bpo-mode" value="delivery">🛵 ' + esc(L.delivery) + "</label></div>";
    } else {
      modes = '<p style="margin:6px 0 12px;font-weight:700">' + esc(mode === "pickup" ? "🛍 " + L.pickup_from : "🛵 " + L.home_delivery) + "</p>";
    }
    var sub = subtotal(), f = fee(), min = parseFloat(cfg.minimum || 0);
    box.innerHTML = '<div class="bpo-head"><h3>' + esc(L.your_order) + '</h3><button class="bpo-x" type="button" data-close aria-label="' + esc(L.close) + '">✕</button></div>' +
      '<div class="bpo-body">' + (cfg.open ? "" : '<p class="bpo-note">' + esc(L.closed) + (cfg.phone ? " " + esc(L.call.replace("%s", cfg.phone)) : "") + "</p>") +
      (cfg.note ? '<p class="bpo-note">' + esc(cfg.note) + "</p>" : "") + rows +
      '<div class="bpo-sum"><div><span>' + esc(L.items) + "</span><span>" + esc(money(sub)) + "</span></div>" +
      (f ? "<div><span>" + esc(L.delivery) + "</span><span>" + esc(money(f)) + "</span></div>" : "") +
      '<div class="t"><span>' + esc(L.total) + "</span><span>" + esc(money(sub + f)) + "</span></div>" +
      (mode === "delivery" && min && sub < min ? '<div style="color:#b45309">' + esc(L.minimum) + " " + esc(money(min)) + "</div>" : "") + "</div>" +
      (cart.length && cfg.open ? modes + '<div class="bpo-f"><input name="name" placeholder="' + esc(L.name) + '" autocomplete="name" value="' + esc(form.name) + '">' +
        '<input name="phone" type="tel" placeholder="' + esc(L.phone) + '" autocomplete="tel" value="' + esc(form.phone) + '">' +
        (mode === "delivery" ? '<textarea name="address" rows="2" placeholder="' + esc(L.address) + '">' + esc(form.address) + "</textarea>" : "") +
        '<input name="note" placeholder="' + esc(L.note) + '" value="' + esc(form.note) + '"><input class="bpo-hp" name="company_website" tabindex="-1" autocomplete="off"></div>' : "") +
      '<p class="bpo-err" id="bpo-err"></p></div>' +
      (cart.length && cfg.open ? '<div class="bpo-foot"><button class="bpo-go" type="button" data-send' + (sending ? " disabled" : "") + ">" +
        esc(sending ? L.sending : L.place + " · " + money(sub + f)) + '</button><p style="margin:8px 0 0;text-align:center;color:#64748b;font-size:13px">' +
        esc(mode === "delivery" ? L.pay_delivery : L.pay_pickup) + "</p></div>" : "");
  }

  function open() { render(); box.classList.add("on"); bg.classList.add("on"); paintButtons(); }
  function close() { box.classList.remove("on"); bg.classList.remove("on"); if (done) { done = null; } paintButtons(); }
  function readForm() { var els = box.querySelectorAll(".bpo-f input, .bpo-f textarea"); for (var i = 0; i < els.length; i++) if (els[i].name in form) form[els[i].name] = els[i].value; }

  function send() {
    readForm();
    var err = box.querySelector("#bpo-err");
    if (form.name.trim().length < 2) { err.textContent = L.need_name; return; }
    if (form.phone.replace(/\D/g, "").length < 7) { err.textContent = L.need_phone; return; }
    if (mode === "delivery" && form.address.trim().length < 5) { err.textContent = L.need_address; return; }
    var hp = box.querySelector(".bpo-hp");
    sending = true; render(); err = box.querySelector("#bpo-err");
    fetch(cfg.endpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      name: form.name, phone: form.phone, mode: mode, lang: cfg.lang, address: mode === "delivery" ? form.address : "", note: form.note,
      company_website: hp ? hp.value : "", items: cart.map(function (x) { return {id: x.id, qty: x.qty}; })})})
      .then(function (r) { return r.json().catch(function () { return {ok: false, error: L.failed}; }); })
      .then(function (d) {
        sending = false;
        if (d.ok) { done = d; cart = []; save(); render(); paintButtons(); }
        else { render(); box.querySelector("#bpo-err").textContent = d.error || L.failed; }
      })
      .catch(function () { sending = false; render(); box.querySelector("#bpo-err").textContent = L.offline + (cfg.phone ? " " + L.call.replace("%s", cfg.phone) : ""); });
  }

  document.addEventListener("click", function (e) {
    var add = e.target.closest && e.target.closest("[data-bp-add]");
    if (add) {
      e.preventDefault();
      if (!cfg.open) { say(L.closed); return; }
      var id = +add.getAttribute("data-id"), line = find(id);
      if (line) { if (line.qty < 50) line.qty++; }
      else cart.push({id: id, name: add.getAttribute("data-name") || "Item", price: parseFloat(add.getAttribute("data-price") || 0), qty: 1});
      save(); paintButtons(); say(L.added + " " + (add.getAttribute("data-name") || ""));
      return;
    }
    if (e.target === bar || bar.contains(e.target)) { open(); return; }
    if (e.target === bg || (e.target.closest && e.target.closest("[data-close]"))) { close(); return; }
    var t = e.target;
    if (!box.contains(t)) return;
    if (t.getAttribute("data-inc") || t.getAttribute("data-dec")) {
      readForm();
      var l = find(+(t.getAttribute("data-inc") || t.getAttribute("data-dec")));
      if (l) { l.qty += t.getAttribute("data-inc") ? 1 : -1; if (l.qty > 50) l.qty = 50; if (l.qty < 1) cart.splice(cart.indexOf(l), 1); }
      save(); render(); paintButtons();
    } else if (t.hasAttribute("data-send")) { send(); }
  });
  box.addEventListener("change", function (e) {
    if (e.target.name === "bpo-mode") { readForm(); mode = e.target.value; render(); }
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && box.classList.contains("on")) close(); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", paintButtons); else paintButtons();
})();
