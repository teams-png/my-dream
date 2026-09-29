/* Retail / shop POS: product grid, barcode scanning, cart, payment, held
 * sales and an offline queue (IndexedDB) that syncs itself when the
 * internet comes back. Every sale carries a client_id so a retry can never
 * bill twice. */
(function () {
  "use strict";
  const CFG = window.POS_CFG, T = CFG.T;
  const DATA = JSON.parse(document.getElementById("posData").textContent);
  const PRODUCTS = DATA.products;
  const CUR = DATA.company.currency || "";
  const $ = id => document.getElementById(id);
  const cart = {};
  let activeCat = "all", clientId = null, lastSale = null, syncing = false;

  /* ------------------------------------------------------------ helpers */
  function round2(v) { const x = v * 100, f = Math.floor(x + 1e-9), d = x - f; if (Math.abs(d - 0.5) < 1e-7) return (f % 2 === 0 ? f : f + 1) / 100; return Math.round(x) / 100; }
  const money = n => round2(+n || 0).toFixed(2);
  const esc = t => String(t == null ? "" : t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const hue = s => { let h = 0; for (const ch of String(s)) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; };
  const initials = s => String(s).trim().split(/\s+/).slice(0, 2).map(w => w[0] || "").join("").toUpperCase();
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)));
  const label = p => p.name + (p.variant ? " — " + p.variant : (p.colour || p.size ? " — " + [p.colour, p.size].filter(Boolean).join(" / ") : ""));
  let csrf = CFG.csrf; // the CSRF cookie is HttpOnly, so the page carries the token
  const csrftoken = () => csrf;
  async function freshToken() {
    const r = await fetch(CFG.syncUrl, { credentials: "same-origin", cache: "no-store" });
    const d = r.ok && !r.redirected ? await r.json().catch(() => null) : null;
    if (d && d.csrf) csrf = d.csrf;
    return !!(d && d.csrf);
  }
  function toast(msg, err) {
    document.querySelectorAll(".pos-toast").forEach(t => t.remove());
    const el = document.createElement("div");
    el.className = "pos-toast" + (err ? " error" : "");
    el.setAttribute("role", "status");
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, 2600);
  }
  function beep(freq) {
    try {
      const a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator();
      o.connect(a.destination); o.frequency.value = freq || 880; o.start(); o.stop(a.currentTime + 0.06);
    } catch (_) {}
  }
  const online = () => navigator.onLine !== false;

  /* ------------------------------------------------------------ catalogue */
  const CAT_ICONS = [[/phone|mobile|handset/i, "📱"], [/cloth|shirt|dress|wear|fashion|boutique/i, "👕"], [/shoe|foot/i, "👟"],
    [/access|cover|case|charger|cable/i, "🎧"], [/drink|beverage|juice/i, "🥤"], [/snack|chip|sweet|choc/i, "🍿"], [/food|grocery|fruit|veg/i, "🍎"],
    [/home|kitchen|house|clean/i, "🏠"], [/beauty|cosmetic|personal care|skin/i, "💄"], [/book|station/i, "📚"], [/toy|kid/i, "🧸"], [/elect|device|laptop|computer/i, "🔌"],
    [/pharma|medic|health/i, "💊"], [/service|repair/i, "🛠️"]];
  const catIcon = name => (CAT_ICONS.find(([re]) => re.test(name)) || [0, "🏷️"])[1];
  const inCart = id => Object.values(cart).filter(i => i.id === id).reduce((s, i) => s + i.qty, 0);
  const available = p => (p.item_type === "handset" ? p.mobile_units.filter(u => !cart[p.id + "-" + u.id]).length : parseFloat(p.stock) - inCart(p.id));
  const soldOut = p => (p.tracked || p.item_type === "handset") && available(p) <= 0;

  function buildRail() {
    const counts = {};
    PRODUCTS.forEach(p => { counts[p.category_id] = (counts[p.category_id] || 0) + 1; });
    const cats = [{ id: "all", name: T.all, ico: "🛍️", n: PRODUCTS.length }].concat(
      DATA.categories.map(c => ({ id: String(c.id), name: c.name, ico: catIcon(c.name), n: counts[c.id] || 0 })));
    $("catRail").innerHTML = cats.map(c => `<button class="cat-btn${c.id === "all" ? " active" : ""}" type="button" data-category="${c.id}"><span class="cat-ico">${c.ico}</span>${esc(c.name)}<span class="cat-count">${c.n}</span></button>`).join("");
    $("catRail").addEventListener("click", e => {
      const b = e.target.closest(".cat-btn"); if (!b) return;
      $("catRail").querySelectorAll(".cat-btn").forEach(x => x.classList.toggle("active", x === b));
      activeCat = b.dataset.category; filterGrid();
    });
  }

  function buildGrid() {
    $("pos-product-grid").innerHTML = PRODUCTS.map((p, i) => `
      <article class="food-card prod-card" data-id="${p.id}" style="--i:${Math.min(i, 30)};--h:${hue(p.name)}">
        <div class="prod-tile"><span class="ico">${esc(initials(p.name))}</span><span class="stock-pill"></span></div>
        <div class="food-body">
          <div class="food-name">${esc(label(p))}</div>
          <div class="prod-sku">${esc(p.sku)}</div>
          <div class="food-meta"><span class="food-price"><small>${esc(CUR)}</small>${esc(p.price)}</span>
            <button class="food-add" type="button" aria-label="${esc(label(p))}">+</button></div>
        </div>
      </article>`).join("");
    refreshStock();
    filterGrid();
  }

  function refreshStock() {
    document.querySelectorAll(".prod-card").forEach(card => {
      const p = PRODUCTS.find(x => x.id === +card.dataset.id), pill = card.querySelector(".stock-pill");
      const left = available(p), tracked = p.tracked || p.item_type === "handset";
      card.classList.toggle("sold", soldOut(p));
      card.querySelector(".food-add").disabled = soldOut(p);
      pill.hidden = !tracked;
      pill.className = "stock-pill" + (left <= 0 ? " out" : left <= Math.max(p.reorder || 0, 3) ? " low" : "");
      pill.textContent = left <= 0 ? T.out : (left <= Math.max(p.reorder || 0, 3) ? T.low + " · " : "") + (+left.toFixed(3)) + " " + T.inStock;
    });
  }

  function filterGrid() {
    const q = $("pos-search").value.trim().toLowerCase();
    let shown = 0;
    document.querySelectorAll(".prod-card").forEach(card => {
      const p = PRODUCTS.find(x => x.id === +card.dataset.id);
      const ok = (activeCat === "all" || String(p.category_id) === activeCat) &&
        (!q || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q) || (p.variant || "").toLowerCase().includes(q) ||
          (p.mobile_units || []).some(u => u.imei.toLowerCase().includes(q)));
      card.hidden = !ok; if (ok) shown++;
    });
    $("posResults").textContent = shown + " " + T.results;
    $("posNoMatch").hidden = shown > 0;
  }

  /* ------------------------------------------------------------ cart */
  function chooseAndAdd(p, fromEl) {
    if (p.item_type !== "handset") return addToCart(p, null, fromEl);
    const units = p.mobile_units.filter(u => !cart[p.id + "-" + u.id]);
    if (!units.length) return toast(T.noImei, true);
    $("imeiProduct").textContent = label(p);
    $("imeiList").innerHTML = units.map(u => `<button class="pick-row" type="button" data-unit="${u.id}"><span><b>${esc(u.imei)}</b><br><small>${esc(u.condition || "")}${u.warranty_months ? " · " + u.warranty_months + "m" : ""}</small></span><span>＋</span></button>`).join("");
    $("imeiList").onclick = e => {
      const b = e.target.closest("[data-unit]"); if (!b) return;
      $("imeiDialog").close();
      addToCart(p, units.find(u => u.id === +b.dataset.unit), fromEl);
    };
    $("imeiDialog").showModal();
  }

  function addToCart(p, unit, fromEl) {
    const key = unit ? `${p.id}-${unit.id}` : String(p.id);
    if (!cart[key]) {
      cart[key] = { key, id: p.id, name: label(p), sku: p.sku, price: parseFloat(p.price), qty: 0,
        mobile_unit_id: unit ? unit.id : null, imei: unit ? unit.imei : null, isNew: true };
    }
    cart[key].qty = unit ? 1 : cart[key].qty + 1;
    cart[key].isNew = true;
    if (fromEl) fly(fromEl);
    changed();
  }

  function fly(el) {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const from = el.getBoundingClientRect(), to = $("cartCount").getBoundingClientRect();
    if (!to.width) return;
    const dot = document.createElement("div");
    dot.className = "fly-dot";
    dot.style.cssText = `left:${from.left + from.width / 2 - 27}px;top:${from.top + from.height / 2 - 27}px;background:${getComputedStyle(el).backgroundImage !== "none" ? getComputedStyle(el).backgroundImage : "#dbe6ff"};color:#fff;font-weight:900`;
    dot.textContent = el.textContent.trim().slice(0, 2);
    document.body.appendChild(dot);
    dot.animate([{ transform: "none", opacity: 1 }, { transform: `translate(${to.left - from.left - from.width / 2 + 14}px,${to.top - from.top - from.height / 2 + 14}px) scale(.3)`, opacity: .4 }],
      { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)" }).onfinish = () => dot.remove();
  }

  const lines = () => Object.values(cart);
  const cartTotal = () => round2(lines().reduce((s, i) => s + round2(i.price * i.qty), 0));

  function changed() {
    clientId = null; // a different cart is a different sale
    renderCart();
    refreshStock();
  }

  function renderCart() {
    const items = lines(), total = cartTotal(), count = items.reduce((s, i) => s + i.qty, 0);
    $("pos-empty-cart").hidden = items.length > 0;
    $("pos-cart-body").innerHTML = items.map(i => `
      <div class="cart-item${i.isNew ? " is-new" : ""}" data-key="${esc(i.key)}">
        <span class="cart-ico" style="--h:${hue(i.name.split(" — ")[0])}">${esc(initials(i.name))}</span>
        <div class="line-mid">
          <div class="cart-name">${esc(i.name)}</div>
          <div class="cart-note">${i.imei ? "IMEI " + esc(i.imei) : `<span class="each">${money(i.price)} ${T.each}</span>`}</div>
          ${i.imei ? "" : `<div class="row"><div class="cart-qty"><button class="qty-btn" type="button" data-step="-1" aria-label="−">−</button><input type="number" min="0" step="1" value="${i.qty}" aria-label="Qty" data-qty><button class="qty-btn" type="button" data-step="1" aria-label="+">+</button></div></div>`}
        </div>
        <div class="line-side"><span class="cart-price">${money(i.price * i.qty)}</span>
          <button class="remove-btn" type="button" data-remove title="${T.remove}" aria-label="${T.remove}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg></button></div>
      </div>`).join("");
    items.forEach(i => { i.isNew = false; });
    $("cartCount").textContent = count + " " + (count === 1 ? T.item : T.items);
    $("mbCount").textContent = count;
    $("sumItems").textContent = count;
    $("pos-total").textContent = money(total);
    $("mbTotal").textContent = CUR + " " + money(total);
    $("payAmt").textContent = money(total);
    ["pos-checkout-btn", "holdBtn", "clearBtn"].forEach(id => { $(id).disabled = !items.length; });
    const panel = $("cartPanel");
    panel.classList.remove("cart-updated"); void panel.offsetWidth; panel.classList.add("cart-updated");
    if (window.Devices) Devices.display({ type: "cart", lines: items.map(i => ({ qty: i.qty, name: i.name, amount: money(i.price * i.qty) })), breakdown: [], total: money(total) });
  }

  function setQty(key, qty) {
    qty = Math.floor(+qty || 0);
    const item = cart[key]; if (!item) return;
    if (qty <= 0) delete cart[key];
    else {
      const p = PRODUCTS.find(x => x.id === item.id);
      if (p.tracked && qty > parseFloat(p.stock) - (inCart(p.id) - item.qty)) toast(`${item.name} · ${Math.max(0, +(parseFloat(p.stock) - (inCart(p.id) - item.qty)).toFixed(3))} ${T.inStock}`, true);
      item.qty = qty;
    }
    changed();
  }

  $("pos-cart-body").addEventListener("click", e => {
    const row = e.target.closest(".cart-item"); if (!row) return;
    const key = row.dataset.key;
    if (e.target.closest("[data-remove]")) { delete cart[key]; changed(); }
    const step = e.target.closest("[data-step]");
    if (step) setQty(key, cart[key].qty + +step.dataset.step);
  });
  $("pos-cart-body").addEventListener("change", e => {
    if (e.target.matches("[data-qty]")) setQty(e.target.closest(".cart-item").dataset.key, e.target.value);
  });
  $("pos-product-grid").addEventListener("click", e => {
    const card = e.target.closest(".prod-card"); if (!card || card.classList.contains("sold")) return;
    chooseAndAdd(PRODUCTS.find(x => x.id === +card.dataset.id), card.querySelector(".prod-tile"));
  });
  $("clearBtn").addEventListener("click", () => {
    if (!lines().length || !confirm(T.clearAsk)) return;
    for (const k in cart) delete cart[k];
    changed();
  });

  /* ------------------------------------------------------------ scanning */
  const searchInput = $("pos-search");
  let scanTimer = null;

  function confirmScan() {
    const sku = searchInput.value.trim().toLowerCase();
    if (!sku) return false;
    let exact = PRODUCTS.find(p => p.sku.toLowerCase() === sku);
    let scannedUnit = null;
    if (!exact) {
      exact = PRODUCTS.find(p => (scannedUnit = (p.mobile_units || []).find(u => u.imei.toLowerCase() === sku || (u.serial_number || "").toLowerCase() === sku)));
    }
    if (!exact) return false;
    if (exact.item_type === "handset") {
      if (scannedUnit && cart[exact.id + "-" + scannedUnit.id]) scannedUnit = null;
      scannedUnit = scannedUnit || exact.mobile_units.find(u => !cart[exact.id + "-" + u.id]);
      if (!scannedUnit) { toast(T.noImei, true); searchInput.select(); return true; }
    } else if (soldOut(exact)) {
      toast(`${label(exact)} ${T.outOfStock}`, true); beep(220); searchInput.select(); return true;
    }
    addToCart(exact, scannedUnit);
    searchInput.value = "";
    filterGrid();
    toast(`✓ ${label(exact)} ${T.added}`);
    beep(880);
    return true;
  }

  searchInput.addEventListener("input", () => {
    filterGrid();
    clearTimeout(scanTimer);
    scanTimer = setTimeout(confirmScan, 120);
  });
  searchInput.addEventListener("keydown", e => {
    if (e.key !== "Enter") return;
    e.preventDefault(); clearTimeout(scanTimer);
    if (!confirmScan()) { toast(T.notFound, true); beep(220); searchInput.select(); }
  });
  if (window.Devices && Devices.attachScanner) {
    Devices.attachScanner(code => {
      if (document.activeElement === searchInput || document.querySelector("dialog[open]")) return;
      searchInput.value = code;
      if (!confirmScan()) { toast(T.notFound, true); beep(220); }
    });
  }

  /* ------------------------------------------------------------ held sales */
  const HELD_KEY = "bp.pos.held.v1";
  const readHeld = () => { try { return JSON.parse(localStorage.getItem(HELD_KEY)) || []; } catch (_) { return []; } };
  const writeHeld = list => { try { localStorage.setItem(HELD_KEY, JSON.stringify(list)); } catch (_) {} renderHeldCount(); };
  function renderHeldCount() { const n = readHeld().length; $("heldCount").hidden = !n; $("heldCount").textContent = n; }
  function holdCurrent() {
    if (!lines().length) return;
    const list = readHeld();
    list.unshift({ id: uuid(), at: new Date().toISOString(), customer: $("pos-customer").value, customerName: $("pos-customer").selectedOptions[0].text.replace(/^👤\s*/, ""), items: lines(), total: cartTotal() });
    writeHeld(list.slice(0, 30));
    for (const k in cart) delete cart[k];
    $("pos-customer").value = "";
    changed();
    toast("⏸️ " + T.held);
  }
  $("holdBtn").addEventListener("click", holdCurrent);
  $("heldBtn").addEventListener("click", () => {
    const list = readHeld();
    $("heldList").innerHTML = list.length ? list.map(h => `<button class="pick-row" type="button" data-held="${h.id}"><span><b>${esc(h.customerName)}</b><br><small>${new Date(h.at).toLocaleString()} · ${h.items.reduce((s, i) => s + i.qty, 0)} ${T.items}</small></span><b>${money(h.total)}</b></button>`).join("") : `<p>${T.noHeld}</p>`;
    $("heldDialog").showModal();
  });
  $("heldList").addEventListener("click", e => {
    const b = e.target.closest("[data-held]"); if (!b) return;
    const list = readHeld(), h = list.find(x => x.id === b.dataset.held);
    if (lines().length) holdCurrent();
    writeHeld(readHeld().filter(x => x.id !== h.id));
    h.items.forEach(i => { cart[i.key] = { ...i, isNew: true }; });
    $("pos-customer").value = h.customer || "";
    $("heldDialog").close();
    changed();
  });

  /* ------------------------------------------------------------ payment */
  let method = "cash";
  function setMethod(m) {
    method = m;
    $("pos-payment-method").value = m;
    $("paySeg").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.method === m));
    $("cashPanel").hidden = m !== "cash";
    if ($("mobile-payment-details")) {
      $("mobile-payment-details").hidden = !["credit", "installment"].includes(m);
      $("installment-fields").hidden = m !== "installment";
    }
    updateChange();
  }
  $("paySeg").addEventListener("click", e => { const b = e.target.closest("button"); if (b && !b.disabled) setMethod(b.dataset.method); });

  function updateChange() {
    const due = cartTotal(), raw = $("tendered").value, given = raw === "" ? due : +raw, diff = round2(given - due);
    const box = $("changeBox");
    box.classList.toggle("short", diff < 0);
    box.firstElementChild.textContent = diff < 0 ? T.short : T.change;
    $("changeAmt").textContent = money(Math.abs(diff));
  }
  $("tendered").addEventListener("input", updateChange);
  $("quickCash").addEventListener("click", e => { const b = e.target.closest("[data-cash]"); if (b) { $("tendered").value = b.dataset.cash; updateChange(); } });

  function preparePay() {
    const due = cartTotal(), off = !online();
    $("payDue").textContent = CUR + " " + money(due);
    $("payLines").innerHTML = `<div><span>${T.subtotal}</span><span>${money(due)}</span></div><div><span>${T.items}</span><span>${lines().reduce((s, i) => s + i.qty, 0)}</span></div>`;
    $("payCustomer").textContent = "👤 " + $("pos-customer").selectedOptions[0].text.replace(/^👤\s*/, "");
    const notes = [...new Set([due, Math.ceil(due / 5) * 5, Math.ceil(due / 10) * 10, Math.ceil(due / 50) * 50, Math.ceil(due / 100) * 100])].filter(v => v >= due).slice(0, 5);
    $("quickCash").innerHTML = notes.map((v, i) => `<button type="button" data-cash="${v.toFixed(2)}">${i === 0 ? T.exact : money(v)}</button>`).join("");
    $("tendered").value = "";
    $("offlineNote").hidden = !off;
    $("couponWrap").hidden = off;
    $("paySeg").querySelectorAll("[data-online-only]").forEach(b => { b.disabled = off; b.title = off ? T.onlineOnly : ""; });
    if (off && ["credit", "installment"].includes(method)) setMethod("cash"); else setMethod(method);
    showMsg("");
    $("completeBtn").disabled = false;
  }
  function showMsg(text, err) { const m = $("pos-message"); m.hidden = !text; m.textContent = text; m.style.background = err ? "#fee4e2" : ""; m.style.color = err ? "#b42318" : ""; }

  $("pos-checkout-btn").addEventListener("click", () => { if (!lines().length) return; preparePay(); $("payDialog").showModal(); setTimeout(() => (method === "cash" ? $("tendered") : $("completeBtn")).focus(), 60); });
  $("payForm").addEventListener("submit", e => { e.preventDefault(); complete(); });

  function saleBody() {
    const val = id => ($(id) ? $(id).value : null);
    return {
      client_id: clientId || (clientId = uuid()),
      customer_id: val("pos-customer") || null,
      warehouse_id: val("pos-branch"),
      payment_method: method,
      coupon_code: online() ? (val("pos-coupon") || "").trim() : "",
      amount_paid: val("pos-amount-paid"), deposit_method: val("pos-deposit-method"),
      installment_count: val("pos-installment-count"), frequency: val("pos-frequency"), next_due_date: val("pos-next-due"),
      lines: lines().map(i => ({ product_id: i.id, quantity: i.qty, unit_price: i.price, mobile_unit_id: i.mobile_unit_id, name: i.name })),
    };
  }

  async function complete() {
    const items = lines();
    if (!items.length) return showMsg(T.cartEmpty, true);
    const deferred = ["credit", "installment"].includes(method);
    if (deferred && !$("pos-customer").value) return showMsg(T.needCustomer, true);
    const tendered = method === "cash" && $("tendered").value !== "" ? +$("tendered").value : null;
    if (tendered !== null && tendered < cartTotal()) return showMsg(T.short + " " + money(cartTotal() - tendered), true);
    const body = saleBody();
    const canQueue = !deferred && !body.coupon_code;
    $("completeBtn").disabled = true;
    showMsg(T.processing);
    if (!online() && canQueue) return saveOffline(body, tendered);
    let res, data;
    try {
      const ctrl = new AbortController(), timer = setTimeout(() => ctrl.abort(), 20000);
      res = await fetch(CFG.checkoutUrl, { method: "POST", credentials: "same-origin", signal: ctrl.signal,
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken() }, body: JSON.stringify(body) });
      clearTimeout(timer);
      if (res.status === 403 && await freshToken()) {
        res = await fetch(CFG.checkoutUrl, { method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken() }, body: JSON.stringify(body) });
      }
      if (res.status >= 500) throw new TypeError("server " + res.status);
      data = await res.json().catch(() => null);
    } catch (err) {
      // The request may or may not have reached the server: keep it under the same client_id.
      if (canQueue) return saveOffline(body, tendered);
      $("completeBtn").disabled = false;
      return showMsg(T.error, true);
    }
    $("completeBtn").disabled = false;
    if (!data || res.redirected) return showMsg(T.sessionEnded, true);
    if (!res.ok) return showMsg(data.error || T.error, true);
    finish({ online: true, body, data, tendered, total: +data.total });
  }

  /* ------------------------------------------------------------ offline queue */
  const DB = "bookpilot-retail", STORE = "sales";
  function idb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "client_id" });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function tx(mode, fn) {
    const db = await idb();
    return new Promise((resolve, reject) => {
      const t = db.transaction(STORE, mode), out = fn(t.objectStore(STORE));
      t.oncomplete = () => resolve(out && out.result);
      t.onerror = () => reject(t.error);
    });
  }
  const queueAll = () => tx("readonly", s => s.getAll()).then(r => r || []).catch(() => []);
  const queuePut = rec => tx("readwrite", s => s.put(rec));
  const queueDel = id => tx("readwrite", s => s.delete(id));

  function nextOfflineNumber() {
    let dev = "", n = 0;
    try {
      dev = localStorage.getItem("bp.pos.device") || Math.random().toString(36).slice(2, 6).toUpperCase();
      localStorage.setItem("bp.pos.device", dev);
      n = (+localStorage.getItem("bp.pos.offlineSeq") || 0) + 1;
      localStorage.setItem("bp.pos.offlineSeq", n);
    } catch (_) { n = Date.now() % 100000; }
    return `OFF-${dev}-${String(n).padStart(4, "0")}`;
  }

  async function saveOffline(body, tendered) {
    const record = { ...body, offline_number: body.offline_number || nextOfflineNumber(), created_at: new Date().toISOString(),
      total: money(cartTotal()), tendered: tendered, customer_name: $("pos-customer").selectedOptions[0].text.replace(/^👤\s*/, ""),
      cashier: DATA.cashier, status: "pending" };
    try { await queuePut(record); } catch (err) { $("completeBtn").disabled = false; return showMsg(T.error + " (" + err + ")", true); }
    $("completeBtn").disabled = false;
    finish({ online: false, body, record, tendered, total: cartTotal() });
    updatePending();
  }

  async function updatePending() {
    const n = (await queueAll()).length;
    $("pendingChip").hidden = !n;
    $("pendingCount").textContent = n;
  }

  async function sync() {
    if (syncing || !online()) return;
    let queue = await queueAll();
    if (!queue.length) return updatePending();
    syncing = true;
    let booked = 0, attention = 0;
    try {
      if (!await freshToken()) { toast(T.signIn, true); return; }
      while (queue.length) {
        const batch = queue.slice(0, 50);
        const res = await fetch(CFG.syncUrl, { method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken() }, body: JSON.stringify({ sales: batch }) });
        const data = res.ok && !res.redirected ? await res.json().catch(() => null) : null;
        if (!data) { if (res.status === 403 || res.redirected) toast(T.signIn, true); break; }
        for (const r of data.results || []) {
          const rec = batch.find(b => b.client_id === r.client_id);
          if (r.status === "synced" || r.status === "attention") { await queueDel(r.client_id); r.status === "synced" ? booked++ : attention++; }
          else if (rec) { rec.status = "error"; rec.error = r.error; await queuePut(rec); }
        }
        queue = queue.slice(50);
      }
    } catch (_) { /* still offline: try again later */ } finally { syncing = false; updatePending(); }
    if (booked) toast(`☁ ${booked} ${T.synced}`);
    if (attention) toast(`⚠ ${attention} ${T.attention}`, true);
    updatePending();
  }
  $("pendingChip").addEventListener("click", sync);

  function netState() {
    const on = online();
    $("netChip").textContent = on ? T.online : T.offline;
    $("netChip").classList.toggle("off", !on);
    // the connection is often not usable yet when "online" fires: try twice
    if (on) { setTimeout(sync, 1500); setTimeout(sync, 8000); }
  }
  addEventListener("online", netState);
  addEventListener("offline", netState);
  setInterval(sync, 30000);

  /* ------------------------------------------------------------ done */
  function receiptData(sale) {
    const rec = sale.record;
    const pay = [[T[rec.payment_method] || rec.payment_method, money(rec.tendered != null ? rec.tendered : rec.total)]];
    if (rec.tendered != null) pay.push([T.change, money(rec.tendered - rec.total)]);
    return {
      company: DATA.company, title: T.receipt + " " + rec.offline_number,
      meta: [new Date(rec.created_at).toLocaleString(), T.cashier + ": " + rec.cashier, rec.customer_name, T.savedOffline],
      lines: rec.lines.map(l => ({ qty: l.quantity, name: l.name, amount: money(l.unit_price * l.quantity) })),
      totals: [[T.subtotal, rec.total]], grand_total: rec.total, payments: pay, footer: T.thanks,
    };
  }

  function printSale(sale, auto) {
    if (!window.Devices) { if (sale.online) window.open(`/invoices/${sale.data.invoice_id}/pdf/`, "_blank"); return; }
    const cfg = Devices.load(), cash = sale.body.payment_method === "cash";
    if (auto && !cfg.autoPrintReceipt) { if (cash && cfg.drawer.enabled) Devices.openDrawer().catch(() => {}); return; }
    const job = sale.online
      ? Devices.printReceipt({ dataUrl: `/devices/print/invoice/${sale.data.invoice_id}.json`, htmlUrl: `/invoices/${sale.data.invoice_id}/pdf/`, drawer: cash && auto })
      : Devices.printReceiptData(receiptData(sale), { drawer: cash && auto });
    job.catch(e => toast(T.printer + ": " + e.message, true));
  }

  function finish(sale) {
    lastSale = sale;
    const change = sale.tendered != null ? round2(sale.tendered - sale.total) : 0;
    $("payDialog").close();
    $("doneCheck").classList.toggle("offline", !sale.online);
    $("doneCheck").textContent = sale.online ? "✓" : "📴";
    $("doneTitle").textContent = sale.online ? T.saleDone : T.savedOffline;
    let sub = sale.online ? sale.data.invoice_number : sale.record.offline_number + " · " + T.willSync;
    if (sale.online && parseFloat(sale.data.discount_amount) > 0) sub += ` · ${sale.data.discount_amount} ${T.discount}`;
    if (sale.online && sale.data.points_earned) sub += ` · +${sale.data.points_earned} ${T.points}`;
    $("doneSub").textContent = sub;
    $("doneChange").hidden = !(change > 0);
    $("doneChangeAmt").textContent = CUR + " " + money(change);
    $("doneShare").hidden = !sale.online;
    if (sale.online) $("doneShare").href = `/invoices/${sale.data.invoice_id}/share/`;
    if (window.Devices) Devices.display({ type: "paid", total: money(sale.total), paid: money(sale.tendered != null ? sale.tendered : sale.total), change: money(Math.max(0, change)) });
    printSale(sale, true);
    // what was sold is no longer on the shelf
    lines().forEach(i => {
      const p = PRODUCTS.find(x => x.id === i.id);
      if (i.mobile_unit_id) p.mobile_units = p.mobile_units.filter(u => u.id !== i.mobile_unit_id);
      else p.stock = String(parseFloat(p.stock) - i.qty);
    });
    for (const k in cart) delete cart[k];
    if ($("pos-coupon")) $("pos-coupon").value = "";
    $("pos-customer").value = "";
    document.body.classList.remove("ticket-open");
    changed();
    $("doneDialog").showModal();
    $("doneNew").focus();
  }
  $("donePrint").addEventListener("click", () => lastSale && printSale(lastSale, false));
  $("doneNew").addEventListener("click", () => { $("doneDialog").close(); });
  $("doneDialog").addEventListener("close", () => searchInput.focus());

  /* ------------------------------------------------------------ chrome */
  document.addEventListener("click", e => {
    const closer = e.target.closest("[data-close]"); if (closer) closer.closest("dialog").close();
    if (e.target.tagName === "DIALOG") e.target.close();
    if (e.target.closest("[data-ticket-toggle]")) document.body.classList.toggle("ticket-open");
  });
  document.addEventListener("keydown", e => {
    if (e.key === "F2") { e.preventDefault(); searchInput.focus(); searchInput.select(); }
    if (e.key === "F9" && !document.querySelector("dialog[open]")) { e.preventDefault(); $("pos-checkout-btn").click(); }
  });
  $("posFullScreen").addEventListener("click", () => { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.(); });

  buildRail();
  buildGrid();
  renderCart();
  renderHeldCount();
  netState();
  updatePending();
})();
