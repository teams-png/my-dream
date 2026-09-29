/*
 * BookPilot offline restaurant POS.
 *
 * Works without internet: the menu comes from the last saved copy, bills are
 * stored in IndexedDB on this device, KOTs and receipts print locally, and
 * everything is sent to the server (idempotently) when the connection returns.
 */
(function () {
  "use strict";
  const CFG = window.OFFLINE_CFG, T = CFG.T;
  const DB_NAME = "bookpilot-offline", PAGE_CACHE = "bp-offline-pos-v1";
  const $ = id => document.getElementById(id);
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------- storage */
  let dbp = null;
  function db() {
    if (dbp) return dbp;
    dbp = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const d = req.result;
        if (!d.objectStoreNames.contains("bills")) d.createObjectStore("bills", { keyPath: "client_id" });
        if (!d.objectStoreNames.contains("meta")) d.createObjectStore("meta");
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return dbp;
  }
  async function tx(store, mode, fn) {
    const d = await db();
    return new Promise((resolve, reject) => {
      const t = d.transaction(store, mode), s = t.objectStore(store);
      let out;
      Promise.resolve(fn(s)).then(v => { out = v; });
      t.oncomplete = () => resolve(out);
      t.onerror = () => reject(t.error);
    });
  }
  const req2p = r => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
  const getMeta = k => tx("meta", "readonly", s => req2p(s.get(k)));
  const setMeta = (k, v) => tx("meta", "readwrite", s => { s.put(v, k); });
  const saveBill = b => { b.updated_at = new Date().toISOString(); return tx("bills", "readwrite", s => { s.put(b); }); };
  const allBills = () => tx("bills", "readonly", s => req2p(s.getAll()));

  /* ------------------------------------------------------------ helpers */
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === "x" ? r : (r & 3 | 8)).toString(16); }));
  function round2(v) { const x = v * 100, f = Math.floor(x + 1e-9), d = x - f; if (Math.abs(d - 0.5) < 1e-7) return (f % 2 === 0 ? f : f + 1) / 100; return Math.round(x) / 100; }
  const money = n => (Math.round((+n || 0) * 100) / 100).toFixed(2);
  const esc = t => String(t == null ? "" : t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function toast(msg, err) {
    document.querySelectorAll(".pos-toast").forEach(t => t.remove());
    const t = document.createElement("div"); t.className = "pos-toast" + (err ? " error" : ""); t.textContent = (err ? "⚠️ " : "✓ ") + msg;
    document.body.appendChild(t); setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, 2800);
  }
  function deviceCode() {
    let c = null;
    try { c = localStorage.getItem("bp.deviceCode"); } catch (e) { /* storage blocked */ }
    if (!c) { c = Math.random().toString(36).slice(2, 6).toUpperCase(); try { localStorage.setItem("bp.deviceCode", c); } catch (e) { /* ignore */ } }
    return c;
  }
  async function nextNumber() {
    const n = ((await getMeta("counter")) || 0) + 1;
    await setMeta("counter", n);
    return `OFF-${deviceCode()}-${String(n).padStart(4, "0")}`;
  }

  /* --------------------------------------------------------------- state */
  let boot = null, bills = [], current = null, category = "all", online = navigator.onLine, syncing = false, authLost = false;
  const item = pid => boot.items.find(i => i.product_id === pid);
  const lineTotal = l => (+l.quantity) * ((+l.unit_price) + (+l.modifier_total || 0));
  function totals(b, override) {
    const o = Object.assign({ sc: +b.service_charge || 0, tip: +b.tip_amount || 0, disc: +b.discount_amount || 0 }, override || {});
    const sub = b.lines.reduce((s, l) => s + lineTotal(l), 0);
    const tax = round2((sub + o.sc + o.tip) * (+b.tax_percent || 0) / 100);
    return { sub: round2(sub), sc: o.sc, tip: o.tip, disc: o.disc, tax, total: round2(Math.max(0, sub + o.sc + o.tip + tax - o.disc)) };
  }
  const openBills = () => bills.filter(b => b.company_id === boot.company.id && b.status === "open").sort((a, b) => a.created_at.localeCompare(b.created_at));

  async function newBill() {
    const b = {
      client_id: uuid(), company_id: boot.company.id, offline_number: await nextNumber(), created_at: new Date().toISOString(),
      channel: "takeaway", table_id: null, table_name: "", guests: 0, tax_percent: boot.tax_percent, lines: [], sent_line_ids: [],
      service_charge: "0.00", tip_amount: "0.00", discount_amount: "0.00", paid: false, payments: [], status: "open", sync: "local", server: {},
    };
    bills.push(b); current = b; await saveBill(b); render();
  }

  /* ------------------------------------------------------------- loading */
  async function loadBoot() {
    if (online) {
      try {
        const r = await fetch(CFG.bootstrapUrl, { credentials: "same-origin", headers: { Accept: "application/json" } });
        if (r.redirected || !(r.headers.get("content-type") || "").includes("json")) { authLost = true; throw new Error("auth"); }
        boot = await r.json(); authLost = false;
        await setMeta("boot:" + boot.company.id, boot); await setMeta("boot", boot);
        warmCache(boot);
        return;
      } catch (e) { /* fall back to the saved copy */ }
    }
    boot = await getMeta("boot");
    if (!boot && "caches" in window) {  // saved in the background by the dashboard / POS
      try { const hit = await caches.match(CFG.bootstrapUrl); if (hit) { boot = await hit.json(); await setMeta("boot", boot); } } catch (e) { /* none saved */ }
    }
  }
  function warmCache(b) {
    if (!("caches" in window)) return;
    caches.open(PAGE_CACHE).then(c => {
      c.add(CFG.pageUrl).catch(() => {});
      document.querySelectorAll('script[src^="/static/"],link[href^="/static/"]').forEach(el => { const u = el.getAttribute("src") || el.getAttribute("href"); c.match(u).then(hit => hit || c.add(u).catch(() => {})); });
      b.items.filter(i => i.image).forEach(i => c.match(i.image).then(hit => hit || c.add(i.image).catch(() => {})));
    });
  }

  /* ---------------------------------------------------------------- menu */
  const ICONS = [["burger", "🍔"], ["pizza", "🍕"], ["drink", "🥤"], ["juice", "🧃"], ["coffee", "☕"], ["tea", "🍵"], ["dessert", "🍨"], ["cake", "🍰"], ["breakfast", "🥞"], ["chicken", "🍗"], ["side", "🍟"], ["wrap", "🌯"], ["salad", "🥗"], ["kid", "🧒"], ["combo", "🍱"], ["rice", "🍚"], ["biryani", "🍛"], ["curry", "🍛"], ["fish", "🐟"], ["soup", "🍲"], ["grill", "🔥"], ["sandwich", "🥪"], ["pasta", "🍝"], ["noodle", "🍜"]];
  const icon = name => (ICONS.find(([k]) => name.toLowerCase().includes(k)) || [0, "🍴"])[1];
  function renderMenu() {
    $("noMenu").hidden = !!(boot && boot.items.length);
    if (!boot) return;
    $("rail").innerHTML = `<button class="cat-btn${category === "all" ? " active" : ""}" data-cat="all"><span class="cat-ico">🍽️</span>${esc(T.all)}</button>` +
      boot.categories.map(c => `<button class="cat-btn${String(category) === String(c.id) ? " active" : ""}" data-cat="${c.id}"><span class="cat-ico">${icon(c.name)}</span>${esc(c.name)}</button>`).join("");
    const q = $("menuSearch").value.toLowerCase().trim();
    const list = boot.items.filter(i => (category === "all" || String(i.category_id) === String(category)) && (i.name + " " + i.sku).toLowerCase().includes(q));
    $("foodGrid").innerHTML = list.map((i, n) => `<article class="food-card${i.available ? "" : " sold"}" style="--i:${Math.min(n, 14)}"><div class="food-image"><div class="food-badges">${i.featured ? '<span class="featured-label">★</span>' : ""}${i.veg ? '<span class="veg-label">●</span>' : ""}${i.available ? "" : `<span class="sold-label">${esc(T.soldOut)}</span>`}</div>${i.image ? `<img src="${esc(i.image)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'food-placeholder',textContent:'🍽️'}))">` : '<span class="food-placeholder">🍽️</span>'}</div><div class="food-body"><div class="food-name">${esc(i.name)}</div><div class="food-meta"><div class="food-price"><small>${esc(boot.company.currency)}</small>${esc(i.price)}</div><button class="food-add" type="button" data-pid="${i.product_id}" ${i.available ? "" : "disabled"} aria-label="${esc(i.name)}">+</button></div></div></article>`).join("");
  }

  /* -------------------------------------------------------------- ticket */
  function render() {
    renderNet(); renderTabs();
    if (!boot) { renderMenu(); return; }
    const b = current;
    $("billTitle").textContent = b ? b.offline_number : "";
    document.querySelectorAll("[data-channel]").forEach(x => x.classList.toggle("on", b && x.dataset.channel === b.channel));
    $("dineFields").hidden = !b || b.channel !== "dine_in";
    $("tableSel").innerHTML = `<option value="">${esc(T.selectTable)}</option>` + boot.tables.map(t => `<option value="${t.id}" ${b && b.table_id === t.id ? "selected" : ""}>${esc(t.name)} · ${esc(t.area)}</option>`).join("");
    $("guests").value = b && b.guests ? b.guests : "";
    const lines = b ? b.lines : [];
    $("empty").hidden = lines.length > 0; $("lines").hidden = !lines.length;
    $("lines").innerHTML = lines.map(l => {
      const sent = b.sent_line_ids.includes(l.id);
      return `<div class="cart-item" data-line="${l.id}">${sent ? `<span class="cart-qty-static">${esc(l.quantity)}×</span>` :
        `<div class="qty-actions"><button class="qty-btn" data-inc="${l.id}">+</button><span class="qty-val">${esc(l.quantity)}</span><button class="qty-btn" data-dec="${l.id}">−</button></div>`}
        <div><div class="cart-name">${esc(l.name)}${sent ? ` <span class="sent-tag">✓ ${esc(T.sent)}</span>` : ""}</div><div class="cart-note">${esc(boot.company.currency)} ${money(+l.unit_price + (+l.modifier_total || 0))}${l.modifier_names && l.modifier_names.length ? " · " + esc(l.modifier_names.join(", ")) : ""}${l.notes ? `<br><span class="note">📝 ${esc(l.notes)}</span>` : ""}</div></div>
        <div class="line-side"><span class="cart-price">${money(lineTotal(l))}</span></div></div>`;
    }).join("");
    const t = b ? totals(b) : { sub: 0, sc: 0, tip: 0, tax: 0, disc: 0, total: 0 };
    $("sums").innerHTML = `<div class="sum-row"><span>${esc(T.subtotal)}</span><span>${money(t.sub)}</span></div>` + (t.tax ? `<div class="sum-row"><span>${esc(T.tax)} (${esc(b.tax_percent)}%)</span><span>+${money(t.tax)}</span></div>` : "");
    $("total").textContent = `${boot.company.currency} ${money(t.total)}`;
    const count = lines.reduce((s, l) => s + (+l.quantity), 0);
    $("cartCount").textContent = `${count} ${count === 1 ? T.item : T.items}`;
    $("mbCount").textContent = count; $("mbTotal").textContent = `${boot.company.currency} ${money(t.total)}`; $("mbNo").textContent = b ? b.offline_number : "";
    $("sendKitchen").disabled = !lines.some(l => !b.sent_line_ids.includes(l.id));
    $("payBtn").disabled = $("printBill").disabled = !lines.length;
    $("payBtn").textContent = `💳 ${T.charge} ${boot.company.currency} ${money(t.total)}`;
    Devices.display({ type: "cart", lines: lines.map(l => ({ qty: l.quantity, name: l.name, amount: money(lineTotal(l)) })), breakdown: [], total: money(t.total) });
  }
  function renderTabs() {
    if (!boot) { $("billTabs").innerHTML = ""; return; }
    $("billTabs").innerHTML = openBills().map(b => {
      const t = totals(b).total;
      return `<button class="bill-tab${current && current.client_id === b.client_id ? " on" : ""}" data-bill="${b.client_id}">${esc(b.channel === "dine_in" && b.table_name ? T.tableLabel + " " + b.table_name : b.offline_number)}<small>${esc(boot.company.currency)} ${money(t)}</small></button>`;
    }).join("");
  }
  function renderNet() {
    const net = $("net");
    net.classList.toggle("off", !online);
    net.querySelector("span").textContent = online ? T.online : T.offline;
    const mine = boot ? bills.filter(b => b.company_id === boot.company.id) : [];
    const waiting = mine.filter(b => b.sync === "pending" || b.sync === "error").length;
    const attention = mine.filter(b => b.sync === "attention").length;
    $("syncChip").innerHTML = syncing ? esc(T.syncing) : waiting ? `<b>${waiting}</b> ${esc(T.waiting)}` : attention ? `<b style="color:#b42318">${attention}</b> ${esc(T.attention)}` : esc(T.allSynced);
    const banner = $("banner");
    if (authLost) { banner.hidden = false; banner.innerHTML = `🔐 ${esc(T.signIn)} <a href="${CFG.loginUrl}?next=${encodeURIComponent(CFG.pageUrl)}">→</a>`; }
    else if (!online) { banner.hidden = false; banner.textContent = "📴 " + T.offlineBanner; }
    else if (openBills().length === 0 || openBills().every(b => !b.lines.length)) { banner.hidden = false; banner.innerHTML = `🟢 ${esc(T.onlineBanner)} <a href="${$("onlineLink").getAttribute("href")}">↩</a>`; }
    else banner.hidden = true;
  }

  /* ------------------------------------------------------------- actions */
  let dlgItem = null;
  function addItem(pid) {
    const i = item(pid); if (!i || !i.available || !current) return;
    if (i.groups.length) {
      dlgItem = i; $("dlgTitle").textContent = i.name; $("dlgQty").value = 1; $("dlgNote").value = ""; $("dlgErr").hidden = true;
      $("dlgGroups").innerHTML = i.groups.map((g, gi) => `<div class="modifier-list" data-g="${gi}"><strong>${esc(g.name)}${g.min ? " *" : ""} <small>(${g.min}–${g.max})</small></strong>${g.options.map(o => `<label class="modifier-choice"><input type="checkbox" value="${o.id}" data-name="${esc(o.name)}" data-price="${esc(o.price)}"> ${esc(o.name)} <strong>+${esc(o.price)}</strong></label>`).join("")}</div>`).join("");
      $("itemDialog").showModal(); return;
    }
    pushLine(i, 1, [], "");
  }
  function pushLine(i, qty, mods, notes) {
    const key = i.product_id + "|" + mods.map(m => m.id).sort().join(",") + "|" + notes;
    const same = current.lines.find(l => l.key === key && !current.sent_line_ids.includes(l.id));
    if (same) same.quantity = String((+same.quantity) + qty);
    else current.lines.push({ id: uuid(), key, product_id: i.product_id, name: i.name, quantity: String(qty), unit_price: i.price,
      modifier_ids: mods.map(m => m.id), modifier_names: mods.map(m => m.name), modifier_total: money(mods.reduce((s, m) => s + (+m.price), 0)), notes });
    current.sync = current.sync === "synced" ? "pending" : current.sync;
    saveBill(current); render(); toast(i.name + " · " + T.added);
    const card = document.querySelector(`[data-pid="${i.product_id}"]`)?.closest(".food-card");
    if (card && !reduceMotion) card.animate([{ transform: "scale(1)" }, { transform: "scale(.94)" }, { transform: "scale(1)" }], { duration: 260 });
  }
  function kotData(b, lines, round) {
    const meta = [b.offline_number, b.channel === "dine_in" ? `${T.tableLabel} ${b.table_name}` : T.takeaway];
    if (b.guests) meta.push(`${T.guests} ${b.guests}`);
    if (round > 1) meta.push(`*** ADD-ON ${round} ***`);
    meta.push(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), T.offlineBill);
    return { title: T.kitchenOrder, meta, lines: lines.map(l => ({ qty: l.quantity, name: l.name, extra: (l.modifier_names || []).map(n => "+ " + n).concat(l.notes ? ["NOTE: " + l.notes] : []) })) };
  }
  function receiptData(b) {
    const t = totals(b), c = boot.company;
    const totalsRows = [[T.subtotal, money(t.sub)]];
    if (t.sc) totalsRows.push([T.service, money(t.sc)]); if (t.tip) totalsRows.push([T.tip, money(t.tip)]);
    if (t.tax) totalsRows.push([`${T.tax} ${b.tax_percent}%`, money(t.tax)]); if (t.disc) totalsRows.push([T.discount, "-" + money(t.disc)]);
    return { kind: "receipt", company: { name: c.name, address: c.address, phone: c.phone, currency: c.currency, vat_number: c.vat_number },
      title: b.offline_number, meta: [new Date(b.paid_at || b.created_at).toLocaleString(), b.channel === "dine_in" ? `${T.tableLabel} ${b.table_name}` : T.takeaway],
      lines: b.lines.map(l => ({ qty: l.quantity, name: l.name, amount: money(lineTotal(l)), extra: (l.modifier_names || []).map(n => "+ " + n) })),
      totals: totalsRows, grand_total: money(t.total), payments: (b.payments || []).map(p => [p.method.toUpperCase(), money(p.amount)]),
      footer: T.thanks, open_drawer: (b.payments || []).some(p => p.method === "cash") };
  }
  async function sendKitchen() {
    const b = current, fresh = b.lines.filter(l => !b.sent_line_ids.includes(l.id));
    if (!fresh.length) return toast(T.noNewItems, true);
    if (b.channel === "dine_in" && !b.table_id) return toast(T.selectTable, true);
    const round = (b.kot_rounds || 0) + 1;
    try { await Devices.printKotData(kotData(b, fresh, round)); } catch (e) { toast(e.message === "raw-unavailable" ? "Printer" : e.message, true); }
    const now = new Date().toISOString();
    fresh.forEach(l => { b.sent_line_ids.push(l.id); l.sent_at = now; });
    b.kot_rounds = round; b.sync = "pending";
    await saveBill(b); render(); toast(T.kotPrinted);
  }

  /* ------------------------------------------------------------- payment */
  let method = "cash";
  function payState() {
    const b = current, o = { sc: +$("paySc").value || 0, tip: +$("payTip").value || 0, disc: +$("payDisc").value || 0 }, t = totals(b, o);
    $("payDue").textContent = `${boot.company.currency} ${money(t.total)}`;
    $("payLines").innerHTML = `<div><span>${esc(T.subtotal)}</span><span>${money(t.sub)}</span></div>` + (t.tax ? `<div><span>${esc(T.tax)}</span><span>+${money(t.tax)}</span></div>` : "");
    document.querySelectorAll("#payDialog .seg button").forEach(x => x.classList.toggle("on", x.dataset.method === method));
    document.querySelector("[data-panel=cash]").hidden = method !== "cash"; document.querySelector("[data-panel=split]").hidden = method !== "split";
    let ok = t.total > 0, payments = [];
    if (method === "cash") {
      payments = [{ method: "cash", amount: money(t.total) }];
      const given = parseFloat($("cashGiven").value);
      if (isNaN(given)) { $("changeAmt").textContent = "—"; $("changeBox").classList.remove("short"); }
      else { const ch = round2(given - t.total); $("changeBox").classList.toggle("short", ch < 0); $("changeLbl").textContent = ch < 0 ? T.still : T.change; $("changeAmt").textContent = money(Math.abs(ch)); ok = ok && ch >= 0; }
      const opts = [...new Set([t.total, Math.ceil(t.total / 5) * 5, Math.ceil(t.total / 10) * 10, Math.ceil(t.total / 50) * 50, Math.ceil(t.total / 100) * 100])].filter(v => v > 0).slice(0, 5);
      $("quickCash").innerHTML = opts.map((v, i) => `<button type="button" data-cash="${v}">${i === 0 ? esc(T.exact) : money(v)}</button>`).join("");
    } else if (method === "split") {
      const v = k => +(document.querySelector(`.split-in[data-for=${k}]`).value) || 0;
      payments = ["cash", "card", "bank"].filter(k => v(k) > 0).map(k => ({ method: k, amount: money(v(k)) }));
      const left = round2(t.total - payments.reduce((s, p) => s + (+p.amount), 0));
      ok = ok && Math.abs(left) < 0.005;
      $("splitLeft").className = "split-left " + (ok ? "ok" : "bad");
      $("splitLeft").textContent = ok ? T.match : (left > 0 ? T.remaining : T.over) + " " + money(Math.abs(left));
    } else payments = [{ method, amount: money(t.total) }];
    $("payGo").disabled = !ok; $("payGo").textContent = `${T.charge} ${boot.company.currency} ${money(t.total)}`;
    return { ok, payments, o, t };
  }
  function openPay() {
    const b = current; if (!b.lines.length) return toast(T.emptyBill, true);
    method = "cash"; $("cashGiven").value = "";
    document.querySelectorAll(".split-in").forEach(x => x.value = "");
    const scPct = +boot.service_charge_percent || 0;
    $("paySc").value = b.channel === "dine_in" && scPct ? money(round2(totals(b).sub * scPct / 100)) : money(b.service_charge);
    $("payTip").value = money(b.tip_amount); $("payDisc").value = money(b.discount_amount);
    $("payFor").textContent = b.offline_number; payState(); $("payDialog").showModal();
  }
  async function charge() {
    const s = payState(); if (!s.ok) return;
    const b = current;
    b.service_charge = money(s.o.sc); b.tip_amount = money(s.o.tip); b.discount_amount = money(s.o.disc);
    b.payments = s.payments; b.paid = true; b.paid_at = new Date().toISOString(); b.status = "paid"; b.sync = "pending";
    b.sent_line_ids = b.lines.map(l => l.id);
    await saveBill(b); $("payDialog").close();
    const cfg = Devices.load(), given = parseFloat($("cashGiven").value), change = isNaN(given) ? 0 : round2(given - s.t.total);
    const paidCash = b.payments.some(p => p.method === "cash");
    if (cfg.autoPrintReceipt) Devices.printReceiptData(receiptData(b), { drawer: paidCash }).catch(e => toast(e.message, true));
    else if (paidCash && cfg.drawer.enabled) Devices.openDrawer().catch(() => {});
    Devices.display({ type: "paid", total: money(s.t.total), paid: isNaN(given) ? money(s.t.total) : money(given), change: money(Math.max(0, change)) });
    toast(`${T.paidOk}${change > 0 ? ` · ${T.change}: ${money(change)}` : ""}`);
    const next = openBills().find(x => x.client_id !== b.client_id);
    if (next) { current = next; render(); } else await newBill();
    syncSoon();
  }

  /* ---------------------------------------------------------------- sync */
  let timer = null;
  const syncSoon = () => { clearTimeout(timer); timer = setTimeout(syncNow, 800); };
  async function syncNow(manual) {
    if (syncing || !boot) return;
    const due = bills.filter(b => b.company_id === boot.company.id && b.lines.length && (b.sync === "pending" || b.sync === "error" || (b.sync === "local" && b.status === "open" && b.sent_line_ids.length)));
    if (!navigator.onLine) { online = false; renderNet(); return; }
    if (!due.length && !manual) return;
    syncing = true; renderNet();
    try {
      await loadBoot();
      if (authLost || !boot.csrf) throw new Error("auth");
      online = true;
      for (let i = 0; i < due.length; i += 20) {
        const chunk = due.slice(i, i + 20);
        const payload = chunk.map(b => ({ client_id: b.client_id, offline_number: b.offline_number, created_at: b.created_at, channel: b.channel, table_id: b.table_id, guests: b.guests,
          tax_percent: b.tax_percent, lines: b.lines.map(l => ({ id: l.id, product_id: l.product_id, quantity: l.quantity, unit_price: l.unit_price, modifier_ids: l.modifier_ids, notes: l.notes, sent_at: l.sent_at })),
          sent_line_ids: b.sent_line_ids, service_charge: b.service_charge, tip_amount: b.tip_amount, discount_amount: b.discount_amount, paid: b.paid, paid_at: b.paid_at, payments: b.payments }));
        const r = await fetch(CFG.syncUrl, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": boot.csrf }, body: JSON.stringify({ bills: payload }) });
        if (r.redirected || !(r.headers.get("content-type") || "").includes("json")) { authLost = true; break; }
        const data = await r.json();
        for (const res of data.results || []) {
          const b = bills.find(x => x.client_id === res.client_id); if (!b) continue;
          b.server = res; b.sync = res.status === "synced" ? "synced" : res.status === "attention" ? "attention" : "error";
          if (b.status === "open" && res.status === "synced" && navigator.onLine) b.status = "handed_over";  // continue it in the normal POS
          await saveBill(b);
        }
      }
      if (manual) toast(T.synced);
    } catch (e) {
      if (e.message !== "auth") { online = navigator.onLine; }
    } finally {
      syncing = false;
      if (current && current.status !== "open") current = openBills()[0] || null;
      if (!current) await newBill(); else render();
      renderBillsList();
    }
  }
  function renderBillsList() {
    if (!boot) return;
    const mine = bills.filter(b => b.company_id === boot.company.id && b.lines.length).sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 100);
    $("billsList").innerHTML = mine.length ? mine.map(b => {
      const st = b.sync === "local" ? "open" : b.sync;
      const label = { open: T.open, pending: T.pending, synced: T.synced, attention: T.attention, error: T.error }[st] || st;
      const srv = b.server || {};
      return `<div class="bill-row"><div><strong>${esc(b.offline_number)}</strong> ${srv.order_number ? "→ " + esc(srv.order_number) : ""}<br><small>${new Date(b.created_at).toLocaleString()} · ${esc(b.status === "paid" ? T.paid : T.open)} · ${esc(boot.company.currency)} ${money(totals(b).total)}</small>${srv.error ? `<br><small style="color:#b42318">${esc(srv.error)}</small>` : ""}</div>
        <div style="text-align:end"><span class="st ${st}">${esc(label)}</span><br>${b.status === "paid" ? `<button class="bill-tab" data-reprint="${b.client_id}">🧾 ${esc(T.reprint)}</button>` : ""}${srv.order_id && b.status !== "paid" ? `<a class="bill-tab" href="${CFG.orderUrl.replace("/0/", "/" + srv.order_id + "/")}">${esc(T.openOnline)}</a>` : ""}</div></div>`;
    }).join("") : `<p class="cart-note">${esc(T.noBills)}</p>`;
  }

  /* -------------------------------------------------------------- events */
  document.addEventListener("click", e => {
    const t = e.target;
    const add = t.closest("[data-pid]"); if (add) { addItem(+add.dataset.pid); return; }
    const cat = t.closest("[data-cat]"); if (cat) { category = cat.dataset.cat; renderMenu(); return; }
    const tab = t.closest("[data-bill]"); if (tab) { current = bills.find(b => b.client_id === tab.dataset.bill); render(); return; }
    const ch = t.closest("[data-channel]"); if (ch && current) { current.channel = ch.dataset.channel; if (current.channel !== "dine_in") { current.table_id = null; current.table_name = ""; } saveBill(current); render(); return; }
    const inc = t.closest("[data-inc]"), dec = t.closest("[data-dec]");
    if (inc || dec) { const id = (inc || dec).dataset[inc ? "inc" : "dec"]; const l = current.lines.find(x => x.id === id); l.quantity = String(+l.quantity + (inc ? 1 : -1)); if (+l.quantity <= 0) current.lines = current.lines.filter(x => x.id !== id); saveBill(current); render(); return; }
    const rp = t.closest("[data-reprint]"); if (rp) { Devices.printReceiptData(receiptData(bills.find(b => b.client_id === rp.dataset.reprint)), { drawer: false }).catch(err => toast(err.message, true)); return; }
    const open = t.closest("[data-open]"); if (open) { renderBillsList(); $(open.dataset.open).showModal(); return; }
    if (t.closest("[data-close]")) { t.closest("dialog").close(); return; }
    if (t.closest("[data-ticket-toggle]")) { document.body.classList.toggle("ticket-open"); return; }
    const qc = t.closest("[data-cash]"); if (qc) { $("cashGiven").value = money(qc.dataset.cash); payState(); return; }
    const seg = t.closest("#payDialog .seg button"); if (seg) { method = seg.dataset.method; if (method === "split" && !document.querySelector(".split-in[data-for=cash]").value) document.querySelector(".split-in[data-for=cash]").value = money(totals(current).total); payState(); return; }
    const q = t.closest("[data-q]"); if (q) { $("dlgQty").value = Math.max(1, (+$("dlgQty").value || 1) + (+q.dataset.q)); }
  });
  $("dlgAdd").addEventListener("click", () => {
    const mods = [];
    for (const [gi, g] of dlgItem.groups.entries()) {
      const picked = [...document.querySelectorAll(`[data-g="${gi}"] input:checked`)].map(x => ({ id: +x.value, name: x.dataset.name, price: x.dataset.price }));
      if (picked.length < g.min || picked.length > g.max) { $("dlgErr").hidden = false; $("dlgErr").textContent = T.chooseOptions + ` (${g.name})`; return; }
      mods.push(...picked);
    }
    $("itemDialog").close(); pushLine(dlgItem, Math.max(1, +$("dlgQty").value || 1), mods, $("dlgNote").value.trim());
  });
  $("tableSel").addEventListener("change", e => { const tb = boot.tables.find(x => String(x.id) === e.target.value); current.table_id = tb ? tb.id : null; current.table_name = tb ? tb.name : ""; saveBill(current); render(); });
  $("guests").addEventListener("change", e => { current.guests = Math.max(0, Math.min(500, +e.target.value || 0)); saveBill(current); });
  $("menuSearch").addEventListener("input", renderMenu);
  $("sendKitchen").addEventListener("click", sendKitchen);
  $("printBill").addEventListener("click", () => Devices.printReceiptData(receiptData(current), { drawer: false }).catch(e => toast(e.message, true)));
  $("payBtn").addEventListener("click", openPay);
  $("payGo").addEventListener("click", charge);
  $("payDialog").addEventListener("input", payState);
  $("newBill").addEventListener("click", async () => { const empty = openBills().find(b => !b.lines.length); if (empty) { current = empty; render(); } else await newBill(); });
  $("syncBtn").addEventListener("click", () => syncNow(true));
  addEventListener("online", () => { online = true; renderNet(); syncNow(); });
  addEventListener("offline", () => { online = false; renderNet(); });
  setInterval(() => { if (navigator.onLine) syncNow(); }, 20000);

  /* ---------------------------------------------------------------- start */
  (async function start() {
    try { await db(); } catch (e) { toast("This browser cannot store offline bills.", true); return; }
    await loadBoot();
    bills = await allBills();
    if (!boot) { render(); return; }
    current = openBills().find(b => !b.lines.length) || openBills()[0] || null;
    if (!current) await newBill(); else render();
    renderMenu(); renderBillsList();
    Devices.attachScanner(code => { const i = boot.items.find(x => x.sku.toLowerCase() === code.toLowerCase().trim()); if (i) addItem(i.product_id); else toast(code, true); });
    if (navigator.onLine) syncNow();
  })();
})();
