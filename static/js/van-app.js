/* Driver's van app: works offline. Actions are kept on the phone (localStorage) with their own id and sent to
   the server when there is a network; the server books each id once. */
(function () {
  "use strict";
  var root = document.getElementById("vanApp");
  if (!root) return;
  var T = JSON.parse(document.getElementById("van-text").textContent);
  var KEY = "van-trip-" + root.dataset.trip, SYNC = root.dataset.sync;
  var fresh = JSON.parse(document.getElementById("van-state").textContent);
  var store = load();
  if (!store.state || (fresh.at || "") >= (store.state.at || "")) store.state = fresh;
  var tab = "shops", sheet = null, syncing = false, notes = [];

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || { ops: [], failed: [], done: [] }; }
    catch (e) { return { ops: [], failed: [], done: [] }; }
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(store)); }
    catch (e) { note(T.photo_big, true); }
  }
  function D(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function m(n) { return (Math.round(n * 100) / 100).toFixed(2); }
  function q(n) { return String(Math.round(n * 1000) / 1000); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function uid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
  }
  function today() { var d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); }
  function cur() { return store.state.currency + " "; }
  function closed() { return store.state.trip.status === "closed"; }
  function note(text, bad) { notes.unshift({ text: text, bad: !!bad }); notes = notes.slice(0, 4); render(); }

  /* the trip as it will be once the waiting actions are sent */
  function view() {
    var s = JSON.parse(JSON.stringify(store.state));
    var shops = {}, items = {};
    s.shops.forEach(function (x) { shops[x.id] = x; });
    s.items.forEach(function (x) { items[x.id] = x; });
    var mo = s.money;
    ["sales", "credit", "paid_cash", "paid_bank", "collected", "expenses", "returns", "expected_cash"].forEach(function (k) { mo[k] = D(mo[k]); });
    store.ops.forEach(function (op) {
      var shop = shops[op.customer];
      if (!shop && op.customer) {
        var o = s.others.filter(function (x) { return String(x.id) === String(op.customer); })[0];
        if (o) { shop = { id: o.id, name: o.name, phone: o.phone, due: "0", limit: "0", late: 0, billed: "", collected: "", prices: {}, orders: [] }; s.shops.push(shop); shops[o.id] = shop; }
      }
      if (op.type === "bill") {
        var total = 0;
        op.lines.forEach(function (l) {
          total += D(l.qty) * D(l.price);
          var it = items[l.product];
          if (it && it.left !== null) it.left = q(D(it.left) - D(l.qty) * D(l.factor || 1));
        });
        var paid = D(op.paid);
        mo.sales += total; mo.credit += total - paid; mo.bills += 1;
        if (op.method === "cash") { mo.paid_cash += paid; mo.expected_cash += paid; } else mo.paid_bank += paid;
        if (shop) { shop.due = m(D(shop.due) + total - paid); shop.billed = m(D(shop.billed) + total); shop.orders = []; }
      } else if (op.type === "collect") {
        mo.collected += D(op.amount); if (op.method === "cash") mo.expected_cash += D(op.amount);
        if (shop) { shop.due = m(D(shop.due) - D(op.amount)); shop.collected = m(D(shop.collected) + D(op.amount)); }
      } else if (op.type === "return") {
        var val = D(op.qty) * D(op.price);
        mo.returns += val;
        if (shop) shop.due = m(D(shop.due) - val);
        var it2 = items[op.product];
        if (op.good && it2 && it2.left !== null) it2.left = q(D(it2.left) + D(op.qty));
      } else if (op.type === "order") {
        if (shop) shop.orders.push({ id: 0, product: op.product, name: (items[op.product] || {}).name, unit: op.unit || "", unit_name: op.unit_name || "", qty: op.qty, note: op.note });
      } else if (op.type === "cancel_order") {
        if (shop) shop.orders = shop.orders.filter(function (o) { return String(o.id) !== String(op.order); });
      } else if (op.type === "expense") {
        mo.expenses += D(op.amount); mo.expected_cash -= D(op.amount);
      } else if (op.type === "start" && s.trip.status === "loading") {
        s.trip.status = "out";
      }
    });
    return s;
  }

  function queue(op) {
    op.id = uid(); op.day = today();
    store.ops.push(op); save();
    sheet = null;
    if (!navigator.onLine) note(T.queued);
    render(); sync();
  }

  function sync(force) {
    if (syncing || navigator.onLine === false) return;
    if (!store.ops.length && !force) return;
    syncing = true; render();
    var sending = store.ops.slice(0, 50);
    fetch(SYNC, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ ops: sending })
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (res) {
      var byId = {};
      (res.results || []).forEach(function (x) { byId[x.id] = x; });
      store.ops = store.ops.filter(function (op) {
        var r = byId[op.id];
        if (!r) return true;
        if (r.ok) { store.done.unshift({ text: r.message, wa: r.wa || "" }); }
        else { store.failed.unshift({ op: op, text: r.message }); }
        return false;
      });
      store.done = store.done.slice(0, 20); store.failed = store.failed.slice(0, 30);
      if (res.state) store.state = res.state;
      save();
      (res.results || []).forEach(function (x) { if (!x.ok) note(T.failed + ": " + x.message, true); });
    }).catch(function () { /* still offline or the server didn't answer: try again later */ })
      .then(function () { syncing = false; render(); if (store.ops.length && navigator.onLine) setTimeout(sync, 4000); });
  }
  function csrf() {
    var c = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return c ? decodeURIComponent(c[1]) : root.dataset.csrf;
  }

  /* ------------------------------------------------------------------ screens */
  function render() {
    var s = view(), h = [];
    var online = navigator.onLine !== false;
    h.push('<div class="va-bar"><h2>' + esc(s.trip.name) + '</h2><span class="vn-pill ' + esc(s.trip.status) + '">' + esc(s.trip.status_label) + "</span>" +
      '<span class="va-net' + (online ? "" : " off") + '">' + (online ? T.online : T.offline) + "</span>" +
      (store.ops.length ? '<span class="va-pend">⏳ ' + store.ops.length + " " + T.waiting + "</span>" : "") +
      (store.ops.length && online ? '<button class="btn btn-secondary" data-act="sync">' + (syncing ? "…" : T.send_now) + "</button>" : "") + "</div>");
    notes.forEach(function (n) { h.push('<div class="va-msg' + (n.bad ? " bad" : "") + '">' + esc(n.text) + "</div>"); });
    if (s.trip.status === "loading" && !closed()) h.push('<button class="btn" style="width:100%;margin-bottom:10px" data-act="start">▶ ' + T.start + "</button>");
    h.push('<div class="va-tabs">' + [["shops", "🏪 " + T.shops], ["van", "📦 " + T.van], ["spend", "⛽ " + T.spend], ["summary", "📊 " + T.summary]]
      .map(function (t) { return '<button data-tab="' + t[0] + '" class="' + (tab === t[0] ? "on" : "") + '">' + t[1] + "</button>"; }).join("") + "</div>");
    if (tab === "shops") h.push(shopsTab(s));
    if (tab === "van") h.push(vanTab(s));
    if (tab === "spend") h.push(spendTab(s));
    if (tab === "summary") h.push(summaryTab(s));
    if (sheet) h.push('<div class="va-sheet" data-close="1"><div>' + sheet(s) + "</div></div>");
    root.innerHTML = h.join("");
  }

  function shopsTab(s) {
    var h = [];
    s.shops.forEach(function (x, i) {
      var due = D(x.due);
      h.push('<div class="va-card"><div class="top"><b>' + (i + 1) + ". " + esc(x.name) + "</b>" +
        (x.phone ? '<a href="tel:' + esc(x.phone) + '" aria-label="' + esc(x.phone) + '">📞</a>' : "") + "</div>" +
        "<small>" + T.owes + " " + cur() + m(due) + "</small> " +
        (x.late ? '<span class="warn">⚠ ' + esc(T.late.replace("%(days)s", x.late)) + "</span> " : "") +
        (x.billed ? '<span class="ok">✓ ' + T.billed + " " + m(D(x.billed)) + "</span> " : "") +
        (x.collected ? '<span class="ok">✓ ' + T.collected + " " + m(D(x.collected)) + "</span> " : "") +
        (x.orders.length ? '<br><small>📝 ' + T.ordered + ": " + x.orders.map(function (o) { return esc(o.name) + " " + esc(o.qty) + (o.unit_name ? " " + esc(o.unit_name) : ""); }).join(", ") + "</small>" : "") +
        (closed() ? "" : '<div class="va-acts"><button class="btn" data-sheet="bill" data-shop="' + x.id + '">🧾 ' + T.bill + "</button>" +
          '<button class="btn btn-secondary" data-sheet="collect" data-shop="' + x.id + '"' + (due > 0 ? "" : " disabled") + ">💰 " + T.collect + "</button>" +
          '<button class="btn btn-secondary" data-sheet="return" data-shop="' + x.id + '">↩ ' + T.return + "</button>" +
          '<button class="btn btn-secondary" data-sheet="order" data-shop="' + x.id + '">📝 ' + T.order + "</button></div>") + "</div>");
    });
    if (!closed() && s.others.length) {
      h.push('<div class="va-card"><label>' + T.other_shop + '<select id="vaOther"><option value="">—</option>' +
        s.others.map(function (o) { return '<option value="' + o.id + '">' + esc(o.name) + (o.phone ? " · " + esc(o.phone) : "") + "</option>"; }).join("") +
        '</select></label><div class="va-acts" style="grid-template-columns:1fr"><button class="btn btn-secondary" data-act="other">🧾 ' + T.bill + "</button></div></div>");
    }
    return h.join("");
  }

  function vanTab(s) {
    var loaded = s.items.some(function (i) { return i.left !== null; });
    if (!loaded) return '<div class="va-card"><small>' + T.no_load + "</small></div>";
    return '<div class="va-card"><table class="va-t"><tr><th>' + T.item + '</th><th class="n">' + T.left + "</th></tr>" +
      s.items.map(function (i) { return "<tr><td>" + esc(i.name) + '</td><td class="n"><b>' + esc(i.left) + "</b></td></tr>"; }).join("") + "</table></div>";
  }

  function spendTab(s) {
    if (closed()) return '<div class="va-card"><small>' + T.closed + "</small></div>";
    return '<div class="va-card"><form id="vaSpend"><label>' + T.kind + '<select name="kind">' +
      s.kinds.map(function (k) { return '<option value="' + k[0] + '">' + esc(k[1]) + "</option>"; }).join("") + "</select></label>" +
      "<label>" + T.amount + '<input name="amount" type="number" min="0.01" step="0.01" inputmode="decimal" required></label>' +
      "<label>" + T.note + '<input name="note" maxlength="200"></label>' +
      "<label>📷 " + T.photo + '<input name="photo" type="file" accept="image/*" capture="environment"></label>' +
      '<button class="btn" style="width:100%;margin-top:12px">' + T.save + "</button></form></div>" +
      '<div class="va-card"><b>' + T.expenses + ": " + cur() + m(s.money.expenses) + "</b></div>";
  }

  function summaryTab(s) {
    var mo = s.money, h = [];
    h.push('<div class="va-card"><table class="va-t">' + [
      [T.bills, mo.bills], [T.sales, cur() + m(mo.sales)], [T.credit, cur() + m(mo.credit)], [T.old_dues, cur() + m(mo.collected)],
      [T.returns, cur() + m(mo.returns)], [T.expenses, cur() + m(mo.expenses)]
    ].map(function (r) { return "<tr><td>" + r[0] + '</td><td class="n">' + r[1] + "</td></tr>"; }).join("") +
      "<tr><th>" + T.cash_due + '</th><th class="n">' + cur() + m(mo.expected_cash) + "</th></tr></table></div>");
    if (store.failed.length) {
      h.push('<div class="va-card"><b>⚠ ' + T.failed + "</b>" + store.failed.map(function (f, i) {
        return '<div class="va-msg bad">' + esc(f.text) + ' <button class="btn btn-secondary" data-drop="' + i + '">' + T.remove + "</button></div>";
      }).join("") + "</div>");
    }
    var recent = store.done.filter(function (d) { return d.wa; }).map(function (d) { return { text: d.text, wa: d.wa }; });
    s.recent.forEach(function (r) { recent.push({ text: r.no + " · " + r.shop + " · " + cur() + r.total, wa: r.wa }); });
    var seen = {};
    recent = recent.filter(function (r) { if (seen[r.wa]) return false; seen[r.wa] = 1; return true; }).slice(0, 15);
    if (recent.length) {
      h.push('<div class="va-card"><b>' + T.recent + "</b>" + recent.map(function (r) {
        return '<div class="va-item" style="display:flex;gap:8px;align-items:center"><span style="flex:1">' + esc(r.text) + '</span><a class="btn btn-secondary" target="_blank" rel="noopener" href="' + esc(r.wa) + '">' + T.whatsapp + "</a></div>";
      }).join("") + "</div>");
    }
    return h.join("");
  }

  function shopOf(s, id) {
    return s.shops.filter(function (x) { return String(x.id) === String(id); })[0] ||
      s.others.filter(function (x) { return String(x.id) === String(id); }).map(function (o) {
        return { id: o.id, name: o.name, phone: o.phone, due: "0", limit: "0", late: 0, prices: {}, orders: [] };
      })[0];
  }
  function unitOptions(item, chosen) {
    return item.units.map(function (u) { return '<option value="' + esc(u.id) + '"' + (String(u.id) === String(chosen || "") ? " selected" : "") + ">" + esc(u.name) + "</option>"; }).join("");
  }
  function unitOf(item, id) { return item.units.filter(function (u) { return String(u.id) === String(id || ""); })[0] || item.units[0]; }
  function priceFor(shop, item, unitId) {
    var u = unitOf(item, unitId);
    if (!u.id && shop.prices && shop.prices[item.id]) return shop.prices[item.id];
    return u.price;
  }
  function head(shop) {
    return "<h3>" + esc(shop.name) + "</h3><small>" + T.owes + " " + cur() + m(D(shop.due)) + "</small>" +
      (shop.late ? ' <span class="warn" style="color:#b91c1c;font-weight:700">⚠ ' + esc(T.late.replace("%(days)s", shop.late)) + "</span>" : "");
  }

  function billSheet(shopId) {
    return function (s) {
      var shop = shopOf(s, shopId), ord = {};
      shop.orders.forEach(function (o) { ord[o.product] = o; });
      var rows = s.items.map(function (it) {
        var o = ord[it.id], unit = o ? o.unit : "";
        return '<div class="va-item" data-item="' + it.id + '"><b>' + esc(it.name) + "</b>" +
          (it.left !== null ? "<small>" + T.in_van + ": " + esc(it.left) + "</small>" : "") +
          (o ? ' <small class="ok" style="color:#166534">📝 ' + T.ordered + " " + esc(o.qty) + "</small>" : "") +
          '<div class="va-row"><input type="number" min="0" step="any" inputmode="decimal" placeholder="' + T.qty + '" data-f="qty" value="' + (o ? esc(o.qty) : "") + '">' +
          '<select data-f="unit"' + (it.units.length < 2 ? " hidden" : "") + ">" + unitOptions(it, unit) + "</select>" +
          '<input type="number" min="0" step="0.01" inputmode="decimal" data-f="price" value="' + esc(priceFor(shop, it, unit)) + '"></div></div>';
      }).join("");
      return head(shop) + '<form id="vaBill" data-shop="' + shop.id + '">' + rows +
        '<div class="va-foot"><div class="tot">' + T.total + ": " + cur() + '<span id="vaTot">0.00</span></div>' +
        '<div class="va-row" style="grid-template-columns:1fr 1fr"><label style="margin:0">' + T.paid_now + '<input type="number" min="0" step="0.01" inputmode="decimal" name="paid" value="0"></label>' +
        '<label style="margin:0">' + T.paid_by + '<select name="method"><option value="cash">' + T.cash + '</option><option value="bank">' + T.bank + "</option></select></label></div>" +
        '<small id="vaCredit"></small><div id="vaErr"></div>' +
        '<div class="btns"><button type="button" class="btn btn-secondary" data-act="full">' + T.full + '</button><button class="btn">✓ ' + T.save_bill + "</button></div>" +
        '<div class="btns"><button type="button" class="btn btn-secondary" data-close="1">' + T.cancel + "</button></div></div></form>";
    };
  }
  function billTotal(form) {
    var t = 0;
    form.querySelectorAll("[data-item]").forEach(function (r) { t += D(r.querySelector('[data-f="qty"]').value) * D(r.querySelector('[data-f="price"]').value); });
    var tot = form.querySelector("#vaTot"); if (tot) tot.textContent = m(t);
    var c = t - D(form.paid.value), cr = form.querySelector("#vaCredit");
    if (cr) cr.textContent = c > 0.004 ? T.on_credit + ": " + m(c) : "";
    return t;
  }
  function submitBill(form) {
    var s = view(), shop = shopOf(s, form.dataset.shop), lines = [], err = "", total = 0;
    var items = {}; s.items.forEach(function (i) { items[i.id] = i; });
    form.querySelectorAll("[data-item]").forEach(function (r) {
      var qty = D(r.querySelector('[data-f="qty"]').value);
      if (!qty) return;
      var it = items[r.dataset.item], u = unitOf(it, r.querySelector('[data-f="unit"]').value), price = D(r.querySelector('[data-f="price"]').value);
      if (it.left !== null && qty * D(u.factor) > D(it.left) + 1e-9) err = T.not_enough + " " + it.name;
      total += qty * price;
      lines.push({ product: it.id, qty: String(qty), unit: u.id, factor: u.factor, price: m(price) });
    });
    var paid = D(form.paid.value), credit = total - paid;
    if (!lines.length) err = T.enter_qty;
    else if (credit > 0.004 && s.block_days && shop.late) err = T.no_credit;
    else if (credit > 0.004 && D(shop.limit) > 0 && D(shop.due) + credit > D(shop.limit)) err = T.over_limit;
    if (paid > total + 0.004) paid = total;
    if (err) { form.querySelector("#vaErr").innerHTML = '<div class="va-err">' + esc(err) + "</div>"; return; }
    queue({ type: "bill", customer: shop.id, lines: lines, paid: m(paid), method: form.method.value });
  }

  function collectSheet(shopId) {
    return function (s) {
      var shop = shopOf(s, shopId);
      return head(shop) + '<form id="vaCollect" data-shop="' + shop.id + '"><label>' + T.amount +
        '<input name="amount" type="number" min="0.01" step="0.01" max="' + m(D(shop.due)) + '" inputmode="decimal" required></label>' +
        "<label>" + T.paid_by + '<select name="method"><option value="cash">' + T.cash + '</option><option value="bank">' + T.bank + "</option></select></label>" +
        '<div class="va-foot"><div class="btns"><button type="button" class="btn btn-secondary" data-close="1">' + T.cancel + '</button><button class="btn">💰 ' + T.collect + "</button></div></div></form>";
    };
  }
  function returnSheet(shopId) {
    return function (s) {
      var shop = shopOf(s, shopId);
      return head(shop) + '<form id="vaReturn" data-shop="' + shop.id + '"><label>' + T.item + '<select name="product">' +
        s.items.map(function (i) { return '<option value="' + i.id + '">' + esc(i.name) + "</option>"; }).join("") + "</select></label>" +
        "<label>" + T.pieces + '<input name="qty" type="number" min="0.001" step="any" inputmode="decimal" required></label>' +
        '<div class="va-choice"><label><input type="radio" name="good" value="1" checked>' + T.good + '</label><label><input type="radio" name="good" value="">' + T.damaged + "</label></div>" +
        "<label>" + T.price_piece + '<input name="price" type="number" min="0" step="0.01" inputmode="decimal"></label>' +
        '<div class="va-foot"><div class="btns"><button type="button" class="btn btn-secondary" data-close="1">' + T.cancel + '</button><button class="btn">↩ ' + T.return + "</button></div></div></form>";
    };
  }
  function orderSheet(shopId) {
    return function (s) {
      var shop = shopOf(s, shopId), first = s.items[0];
      var open = shop.orders.length ? "<label>" + T.open_orders + "</label>" + shop.orders.map(function (o) {
        return '<div class="va-item" style="display:flex;gap:8px;align-items:center"><span style="flex:1">' + esc(o.name) + " · " + esc(o.qty) + " " + esc(o.unit_name) + (o.note ? " · " + esc(o.note) : "") + "</span>" +
          (o.id ? '<button type="button" class="btn btn-secondary" data-cancel-order="' + o.id + '" data-shop="' + shop.id + '">✕</button>' : "") + "</div>";
      }).join("") : "";
      return head(shop) + open + '<form id="vaOrder" data-shop="' + shop.id + '"><label>' + T.item + '<select name="product">' +
        s.items.map(function (i) { return '<option value="' + i.id + '">' + esc(i.name) + "</option>"; }).join("") + "</select></label>" +
        '<div class="va-row" style="grid-template-columns:1fr 1fr"><label style="margin:0">' + T.qty + '<input name="qty" type="number" min="0.001" step="any" inputmode="decimal" required></label>' +
        '<label style="margin:0">&nbsp;<select name="unit">' + (first ? unitOptions(first, "") : "") + "</select></label></div>" +
        "<label>" + T.note + '<input name="note" maxlength="200"></label>' +
        '<div class="va-foot"><div class="btns"><button type="button" class="btn btn-secondary" data-close="1">' + T.cancel + '</button><button class="btn">📝 ' + T.order + "</button></div></div></form>";
    };
  }

  function shrink(file, done) {
    var reader = new FileReader();
    reader.onload = function () {
      var img = new Image();
      img.onload = function () {
        var k = Math.min(1, 1000 / Math.max(img.width, img.height)), c = document.createElement("canvas");
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        done(c.toDataURL("image/jpeg", 0.7));
      };
      img.onerror = function () { done(null); };
      img.src = reader.result;
    };
    reader.onerror = function () { done(null); };
    reader.readAsDataURL(file);
  }

  /* ------------------------------------------------------------------ events */
  root.addEventListener("click", function (e) {
    var t = e.target.closest("button,[data-close],a");
    if (!t) return;
    if (t.dataset.close && (t === e.target || t.tagName === "BUTTON")) { sheet = null; render(); return; }
    if (t.dataset.tab) { tab = t.dataset.tab; render(); return; }
    if (t.dataset.sheet) {
      var id = t.dataset.shop;
      sheet = { bill: billSheet, collect: collectSheet, return: returnSheet, order: orderSheet }[t.dataset.sheet](id);
      render();
      var f = root.querySelector("#vaBill"); if (f) billTotal(f);
      return;
    }
    if (t.dataset.drop !== undefined) { store.failed.splice(+t.dataset.drop, 1); save(); render(); return; }
    if (t.dataset.cancelOrder) { queue({ type: "cancel_order", order: t.dataset.cancelOrder, customer: t.dataset.shop }); return; }
    var act = t.dataset.act;
    if (act === "sync") sync(true);
    if (act === "start") queue({ type: "start" });
    if (act === "other") { var v = root.querySelector("#vaOther").value; if (v) { sheet = billSheet(v); render(); billTotal(root.querySelector("#vaBill")); } }
    if (act === "full") { var fb = root.querySelector("#vaBill"); fb.paid.value = m(billTotal(fb)); billTotal(fb); }
  });
  root.addEventListener("input", function (e) {
    var f = e.target.closest("#vaBill"); if (f) billTotal(f);
  });
  root.addEventListener("change", function (e) {
    var row = e.target.closest("[data-item]");
    if (row && e.target.dataset.f === "unit") {
      var s = view(), form = e.target.closest("form"), shop = shopOf(s, form.dataset.shop);
      var it = s.items.filter(function (i) { return String(i.id) === row.dataset.item; })[0];
      row.querySelector('[data-f="price"]').value = priceFor(shop, it, e.target.value);
      billTotal(form);
    }
    if (e.target.name === "product" && e.target.closest("#vaOrder")) {
      var it2 = view().items.filter(function (i) { return String(i.id) === e.target.value; })[0];
      e.target.closest("form").unit.innerHTML = unitOptions(it2, "");
    }
  });
  root.addEventListener("submit", function (e) {
    e.preventDefault();
    var f = e.target, s = view();
    if (f.id === "vaBill") return submitBill(f);
    if (f.id === "vaCollect") {
      if (D(f.amount.value) <= 0) return;
      return queue({ type: "collect", customer: f.dataset.shop, amount: m(D(f.amount.value)), method: f.method.value });
    }
    if (f.id === "vaReturn") {
      var shop = shopOf(s, f.dataset.shop), it = s.items.filter(function (i) { return String(i.id) === f.product.value; })[0];
      var price = f.price.value !== "" ? D(f.price.value) : D((shop.prices || {})[it.id] || it.units[0].price);
      return queue({ type: "return", customer: shop.id, product: it.id, qty: f.qty.value, good: !!f.querySelector('[name="good"]:checked').value, price: m(price) });
    }
    if (f.id === "vaOrder") {
      var it3 = s.items.filter(function (i) { return String(i.id) === f.product.value; })[0], u = unitOf(it3, f.unit.value);
      return queue({ type: "order", customer: f.dataset.shop, product: it3.id, qty: f.qty.value, unit: u.id, unit_name: u.id ? u.name : "", note: f.note.value });
    }
    if (f.id === "vaSpend") {
      var amount = D(f.amount.value);
      if (amount <= 0) return note(T.enter_amount, true);
      var op = { type: "expense", kind: f.kind.value, amount: m(amount), note: f.note.value };
      var file = f.photo.files && f.photo.files[0];
      if (!file) { queue(op); note("✓ " + T.save); return; }
      shrink(file, function (data) { if (data) op.photo = data; queue(op); note("✓ " + T.save); });
    }
  });
  window.addEventListener("online", function () { render(); sync(true); });
  window.addEventListener("offline", render);
  setInterval(function () { sync(true); }, 60000);
  render();
  sync(true);
})();
