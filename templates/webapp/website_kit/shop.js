/* BookPilot shop for any website (WordPress, Bootstrap, plain HTML): filters, product pages, wishlist, reviews and
   the cart, with products, prices and stock live from BookPilot.
   <div class="bookpilot-shop"></div> + this script. Optional: data-category="12", data-color="#…" */
(function () {
  "use strict";
  if (window.__bpShop) return;
  window.__bpShop = 1;
  var C = {{ cfg|safe }}, T = C.t || {};
  var CSS = ".bps{--c:#0f766e;font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#0f172a}.bps *{box-sizing:border-box}" +
    ".bps a{color:var(--c)}.bps button{font:inherit;cursor:pointer}.bps .lay{display:grid;grid-template-columns:240px minmax(0,1fr);gap:22px;align-items:start}" +
    "@media(max-width:860px){.bps .lay{grid-template-columns:1fr}}" +
    ".bps .side{border:1px solid #e2e8f0;border-radius:14px;padding:10px 14px;background:#fff}.bps .side summary{font-weight:800;cursor:pointer;padding:4px 0}" +
    ".bps .fg{padding:10px 0;border-bottom:1px solid #e2e8f0}.bps .fg:last-child{border:0}.bps .ft{display:block;font-weight:800;font-size:13.5px;margin-bottom:6px}" +
    ".bps .fo{display:flex;gap:8px;align-items:center;font-size:14px;padding:3px 0;cursor:pointer}.bps .fo small{margin-inline-start:auto;color:#64748b}" +
    ".bps input[type=search],.bps input[type=number],.bps select,.bps textarea,.bps .rf input{width:100%;padding:8px 10px;border:1px solid #cbd5e1;border-radius:10px;font:inherit;background:#fff;color:inherit;min-width:0}" +
    ".bps .rng{display:flex;gap:6px;align-items:center}.bps .chips{display:flex;gap:6px;overflow-x:auto;padding-bottom:6px;margin-bottom:10px}" +
    ".bps .chip{white-space:nowrap;border:1px solid #e2e8f0;background:#fff;border-radius:999px;padding:6px 13px;font-weight:600;font-size:14px}.bps .chip.on{background:var(--c);border-color:var(--c);color:#fff}" +
    ".bps .bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}.bps .bar .grow{flex:1;color:#64748b;font-size:14px}.bps .bar select{width:auto}" +
    ".bps .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}@media(max-width:520px){.bps .grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}" +
    ".bps .card{position:relative;background:#fff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;display:flex;flex-direction:column}" +
    ".bps .card .pic{display:block;aspect-ratio:1;background:radial-gradient(circle at 50% 40%,#fff 0,#eef2ef 75%)}.bps .card img{width:100%;height:100%;object-fit:cover}" +
    ".bps img[src*='/static/products/']{object-fit:contain!important;padding:14%}" +
    ".bps .card .b{padding:10px 12px;display:flex;flex-direction:column;gap:4px;flex:1}.bps .card .n{font-weight:700;color:inherit;text-decoration:none}" +
    ".bps .row{display:flex;justify-content:space-between;align-items:center;gap:6px;margin-top:auto;flex-wrap:wrap}.bps .pr{font-weight:800;color:var(--c)}.bps s{color:#94a3b8;font-weight:600;font-size:.85em}" +
    ".bps .add{border:1.5px solid var(--c);background:#fff;color:var(--c);border-radius:999px;padding:6px 12px;font-weight:700;font-size:13.5px}.bps .add:hover,.bps .add.big{background:var(--c);color:#fff}" +
    ".bps .add.big{padding:12px 24px;font-size:16px}.bps .wish{position:absolute;top:8px;inset-inline-end:8px;width:32px;height:32px;border-radius:50%;border:0;background:#fff;box-shadow:0 2px 8px #0002;color:#e11d48;font-size:17px;z-index:2}" +
    ".bps .wish.on{background:#e11d48;color:#fff}.bps .bdg{position:absolute;top:8px;inset-inline-start:8px;display:flex;gap:4px;z-index:2}" +
    ".bps .bdg span{font-size:11px;font-weight:800;padding:3px 8px;border-radius:999px;background:#e11d48;color:#fff}.bps .bdg .low{background:#f59e0b;color:#111}.bps .bdg .out{background:#334155}" +
    ".bps .st{background:linear-gradient(90deg,#f59e0b calc(var(--r)*20%),#cbd5e1 0);-webkit-background-clip:text;background-clip:text;color:transparent;letter-spacing:1px}" +
    ".bps .pg{display:flex;gap:8px;justify-content:center;margin-top:20px}.bps .pg button{border:1px solid #e2e8f0;background:#fff;border-radius:999px;padding:7px 14px}" +
    ".bps .prod{display:grid;grid-template-columns:1fr 1fr;gap:28px}@media(max-width:760px){.bps .prod{grid-template-columns:1fr}}" +
    ".bps .main{aspect-ratio:1;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;background:radial-gradient(circle at 50% 40%,#fff 0,#eef2ef 75%)}.bps .main img{width:100%;height:100%;object-fit:cover}" +
    ".bps .th{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}.bps .th button{width:58px;height:58px;padding:0;border:2px solid #e2e8f0;border-radius:8px;overflow:hidden;background:#fff}.bps .th button.on{border-color:var(--c)}.bps .th img{width:100%;height:100%;object-fit:cover}" +
    ".bps h2{margin:0 0 6px;font-size:26px}.bps .big{font-size:26px;font-weight:800;color:var(--c)}.bps .ok{display:inline-block;background:#dcfce7;color:#166534;border-radius:999px;padding:3px 10px;font-weight:700;font-size:13px}" +
    ".bps .ok.low{background:#fef3c7;color:#92400e}.bps .ok.no{background:#fee2e2;color:#991b1b}.bps table{width:100%;border-collapse:collapse;margin:12px 0}.bps td,.bps th{padding:7px 4px;border-bottom:1px solid #e2e8f0;text-align:start;vertical-align:top}" +
    ".bps .opts{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.bps .opts button{border:1.5px solid #e2e8f0;background:#fff;border-radius:999px;padding:6px 12px;font-weight:600}.bps .opts button.on{border-color:var(--c);color:var(--c)}" +
    ".bps .rv{border-top:1px solid #e2e8f0;padding:10px 0}.bps .rf{display:grid;gap:8px;max-width:520px;margin-top:8px}.bps .wa{display:inline-block;margin-inline-start:8px;padding:12px 18px;border-radius:999px;background:#25d366;color:#fff!important;text-decoration:none;font-weight:700}";
  var root, opts, state = {}, wish = load();

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function load() { try { var w = JSON.parse(localStorage.getItem(C.key) || "[]"); return Array.isArray(w) ? w : []; } catch (e) { return []; } }
  function saveWish() { try { localStorage.setItem(C.key, JSON.stringify(wish)); } catch (e) {} }
  function stars(r) { return '<span class="st" style="--r:' + (+r || 0) + '">★★★★★</span>'; }

  function parseHash() {
    var h = location.hash.replace(/^#/, "");
    if (h.indexOf("bp-product/") === 0) return {view: "product", id: parseInt(h.slice(11), 10)};
    var q = h.indexOf("bp-shop?") === 0 ? h.slice(8) : "";
    return {view: "list", q: new URLSearchParams(q)};
  }
  function go(hash) { if (location.hash !== hash) location.hash = hash; else route(); }
  function listHash(params) { var s = params.toString(); return "#bp-shop" + (s ? "?" + s : ""); }

  function cardHtml(i, cur, ordering) {
    var w = wish.indexOf(i.id) >= 0;
    var badges = (i.was ? '<span>' + esc(T.sale) + "</span>" : "") + (i.available === false ? '<span class="out">' + esc(T.sold_out) + "</span>" : (i.low ? '<span class="low">' + i.stock + " " + esc(T.left) + "</span>" : ""));
    return '<div class="card"><button type="button" class="wish' + (w ? " on" : "") + '" data-w="' + i.id + '">' + (w ? "♥" : "♡") + "</button>" +
      (badges ? '<div class="bdg">' + badges + "</div>" : "") +
      '<a class="pic" href="#bp-product/' + i.id + '"><img loading="lazy" src="' + esc(i.image) + '" alt="' + esc(i.name) + '"></a>' +
      '<div class="b"><a class="n" href="#bp-product/' + i.id + '">' + esc(i.name) + "</a>" +
      (i.rating ? '<span style="font-size:13px;color:#64748b">' + stars(i.rating) + " (" + i.reviews + ")</span>" : "") +
      '<div class="row"><span class="pr">' + esc(cur) + " " + esc(i.price) + (i.was ? " <s>" + esc(i.was) + "</s>" : "") + "</span>" +
      (ordering && i.orderable ? '<button type="button" class="add" data-bp-add data-id="' + i.id + '" data-name="' + esc(i.name) + '" data-price="' + esc(i.price) + '">' + esc(T.add) + "</button>" : "") +
      "</div></div></div>";
  }

  function facetHtml(key, title, list) {
    if (!list || !list.length) return "";
    return '<div class="fg"><span class="ft">' + esc(title) + "</span>" + list.map(function (o) {
      return '<label class="fo"><input type="checkbox" data-f="' + esc(key) + '" value="' + esc(o.value) + '"' + (o.on ? " checked" : "") + "> " + esc(o.label) + " <small>" + o.count + "</small></label>";
    }).join("") + "</div>";
  }

  function renderList(d, q) {
    var f = d.facets, cur = d.currency;
    var cats = d.categories.length > 1 ? '<div class="chips"><button type="button" class="chip' + (!d.category ? " on" : "") + '" data-cat="">' + esc(T.all) + "</button>" +
      d.categories.map(function (c) { return '<button type="button" class="chip' + (d.category === c.id ? " on" : "") + '" data-cat="' + c.id + '">' + esc(c.name) + "</button>"; }).join("") + "</div>" : "";
    var side = '<details class="side"' + (innerWidth > 860 ? " open" : "") + "><summary>⚙ " + esc(T.filters) + "</summary>" +
      '<div class="fg"><input type="search" data-q value="' + esc(q.get("q") || "") + '" placeholder="' + esc(T.search) + '"></div>' +
      '<div class="fg"><span class="ft">' + esc(T.price) + " (" + esc(cur) + ')</span><div class="rng"><input type="number" min="0" data-min value="' + esc(q.get("min") || "") + '" placeholder="' + f.price_lo + '"><span>–</span><input type="number" min="0" data-max value="' + esc(q.get("max") || "") + '" placeholder="' + f.price_hi + '"></div></div>' +
      '<div class="fg"><label class="fo"><input type="checkbox" data-stock' + (q.get("stock") === "1" ? " checked" : "") + "> " + esc(T.in_stock) + "</label></div>" +
      (f.brand.length > 1 ? facetHtml("brand", T.brand, f.brand) : "") + facetHtml("colour", T.colour, f.colour) + facetHtml("size", T.size, f.size) +
      f.attrs.map(function (a) { return facetHtml(a.key, a.label, a.options); }).join("") +
      '<div class="fg" style="display:flex;gap:10px;align-items:center"><button type="button" class="add" data-apply>' + esc(T.apply) + '</button><a href="#bp-shop" data-clear>' + esc(T.clear) + "</a></div></details>";
    var bar = '<div class="bar"><span class="grow">' + (q.get("ids") ? "♥ " + esc(T.wishlist) + " · " : "") + d.total + " " + esc(T.products) + "</span>" +
      (wish.length ? '<button type="button" class="chip" data-wishlist>♥ ' + wish.length + "</button>" : "") +
      '<select data-sort><option value="">' + esc(T.sort_name) + '</option><option value="low">' + esc(T.sort_low) + '</option><option value="high">' + esc(T.sort_high) + '</option><option value="new">' + esc(T.sort_new) + "</option></select></div>";
    var grid = d.items.length ? '<div class="grid">' + d.items.map(function (i) { return cardHtml(i, cur, d.ordering); }).join("") + "</div>" : "<p>" + esc(T.none) + "</p>";
    var pg = d.pages > 1 ? '<div class="pg">' + (d.page > 1 ? '<button type="button" data-page="' + (d.page - 1) + '">← ' + esc(T.prev) + "</button>" : "") + "<span>" + d.page + " / " + d.pages + "</span>" +
      (d.page < d.pages ? '<button type="button" data-page="' + (d.page + 1) + '">' + esc(T.next) + " →</button>" : "") + "</div>" : "";
    root.innerHTML = cats + '<div class="lay">' + side + "<div>" + bar + grid + pg + "</div></div>";
    var sel = root.querySelector("[data-sort]"); sel.value = q.get("sort") || "";
  }

  function readFilters(q) {
    var n = new URLSearchParams();
    ["cat", "sort", "ids"].forEach(function (k) { if (q.get(k)) n.set(k, q.get(k)); });
    var s = root.querySelector("[data-q]").value.trim(); if (s) n.set("q", s);
    var mn = root.querySelector("[data-min]").value, mx = root.querySelector("[data-max]").value;
    if (mn) n.set("min", mn); if (mx) n.set("max", mx);
    if (root.querySelector("[data-stock]").checked) n.set("stock", "1");
    [].forEach.call(root.querySelectorAll("[data-f]:checked"), function (c) { n.append(c.getAttribute("data-f"), c.value); });
    return n;
  }

  function renderProduct(d) {
    var i = d.item, cur = d.currency, w = wish.indexOf(i.id) >= 0;
    var photos = d.photos.length ? '<div class="th">' + d.photos.map(function (p, n) { return '<button type="button" data-pic="' + esc(p) + '"' + (n ? "" : ' class="on"') + '><img src="' + esc(p) + '" alt=""></button>'; }).join("") + "</div>" : "";
    var stock = i.tracked ? (i.stock <= 0 ? '<span class="ok no">' + esc(T.sold_out) + "</span>" : (i.low ? '<span class="ok low">' + i.stock + " " + esc(T.left) + "</span>" : '<span class="ok">✓ ' + esc(T.in_stock_label) + "</span>")) : "";
    var opts = d.options.length > 1 ? "<b>" + esc(T.options) + '</b><div class="opts">' + d.options.map(function (o) { return '<button type="button" data-go="' + o.id + '"' + (o.id === i.id ? ' class="on"' : "") + ">" + esc(o.label) + "</button>"; }).join("") + "</div>" : "";
    var specs = d.specs.length ? "<table>" + d.specs.map(function (s) { return "<tr><td style=\"color:#64748b\">" + esc(s[0]) + "</td><td>" + esc(s[1]) + "</td></tr>"; }).join("") + "</table>" : "";
    var chart = d.size_chart ? "<details><summary style=\"cursor:pointer;font-weight:700\">📏 " + esc(T.size_chart) + "</summary><table>" + d.size_chart.rows.map(function (r, n) { return "<tr>" + r.map(function (c) { return n ? "<td>" + esc(c) + "</td>" : "<th>" + esc(c) + "</th>"; }).join("") + "</tr>"; }).join("") + "</table>" + (d.size_chart.note ? "<p>" + esc(d.size_chart.note) + "</p>" : "") + "</details>" : "";
    var reviews = d.reviews_on ? '<h3 style="margin-top:24px">' + esc(T.reviews) + (i.reviews ? " · " + i.rating + " ★" : "") + "</h3>" +
      (d.reviews.length ? d.reviews.map(function (r) { return '<div class="rv">' + stars(r.rating) + " <b>" + esc(r.name) + '</b> <small style="color:#64748b">' + esc(r.date) + "</small>" + (r.text ? "<p style=\"margin:4px 0 0\">" + esc(r.text) + "</p>" : "") + "</div>"; }).join("") : "<p style=\"color:#64748b\">" + esc(T.no_reviews) + "</p>") +
      '<details><summary style="cursor:pointer;font-weight:700">✍ ' + esc(T.write_review) + '</summary><form class="rf" data-review="' + i.id + '"><input name="name" required maxlength="80" placeholder="' + esc(T.your_name) + '"><select name="rating"><option>5</option><option>4</option><option>3</option><option>2</option><option>1</option></select>' +
      '<textarea name="text" rows="3" maxlength="2000" placeholder="' + esc(T.liked) + '"></textarea><input name="company_website" tabindex="-1" style="position:absolute;left:-9999px"><button class="add big" type="submit">' + esc(T.send_review) + "</button></form></details>" : "";
    var ask = C.whatsapp ? '<a class="wa" target="_blank" rel="noopener" href="https://wa.me/' + C.whatsapp + "?text=" + encodeURIComponent(i.name + " — " + cur + " " + i.price + "\n" + location.href) + '">💬 ' + esc(T.ask) + "</a>" : "";
    root.innerHTML = '<p><a href="#bp-shop" data-back>← ' + esc(T.back) + '</a></p><div class="prod"><div><div class="main"><img data-main src="' + esc(i.image) + '" alt="' + esc(i.name) + '"></div>' + photos + "</div><div>" +
      (i.brand ? '<div style="color:#64748b;font-weight:700;text-transform:uppercase;font-size:12.5px">' + esc(i.brand) + "</div>" : "") + "<h2>" + esc(i.name) + "</h2>" +
      (i.rating ? "<div>" + stars(i.rating) + " " + i.rating + " (" + i.reviews + ")</div>" : "") +
      '<div class="big">' + esc(cur) + " " + esc(i.price) + (i.was ? " <s>" + esc(i.was) + "</s>" : "") + "</div>" + (i.offer ? "<div>🏷 " + esc(i.offer) + "</div>" : "") +
      "<p>" + stock + "</p>" + opts + '<p style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
      (d.ordering && i.orderable ? '<button type="button" class="add big" data-bp-add data-id="' + i.id + '" data-name="' + esc(i.name) + '" data-price="' + esc(i.price) + '">🛒 ' + esc(T.add_cart) + "</button>" : "") +
      '<button type="button" class="add" data-w="' + i.id + '">' + (w ? "♥" : "♡") + "</button>" + ask + "</p>" +
      (i.description ? '<p style="white-space:pre-line">' + esc(i.description) + "</p>" : "") + specs + chart + "</div></div>" + reviews +
      (d.related.length ? '<h3 style="margin-top:24px">' + esc(T.also) + '</h3><div class="grid">' + d.related.map(function (r) { return cardHtml(r, cur, d.ordering); }).join("") + "</div>" : "");
    root.scrollIntoView({behavior: "smooth", block: "start"});
  }

  function fetchJson(url) { return fetch(url, {credentials: "omit"}).then(function (r) { if (!r.ok) throw r; return r.json(); }); }

  function route() {
    state = parseHash();
    if (state.view === "product") {
      fetchJson(C.product.replace("{id}", state.id) + "?lang=" + encodeURIComponent(C.lang)).then(renderProduct).catch(function () { go("#bp-shop"); });
      return;
    }
    var q = state.q;
    if (!q.get("cat") && opts.category) q.set("cat", opts.category);
    q.set("lang", C.lang);
    fetchJson(C.shop + "?" + q.toString()).then(function (d) { q.delete("lang"); renderList(d, q); });
  }

  function onClick(e) {
    var t = e.target, el;
    if ((el = t.closest("[data-w]"))) {
      e.preventDefault();
      var id = +el.getAttribute("data-w"), k = wish.indexOf(id);
      if (k >= 0) wish.splice(k, 1); else wish.push(id);
      saveWish(); el.classList.toggle("on", k < 0); el.textContent = k < 0 ? "♥" : "♡";
      return;
    }
    var q = state.q || new URLSearchParams();
    if ((el = t.closest("[data-cat]"))) { var n = new URLSearchParams(); var c = el.getAttribute("data-cat"); if (c) n.set("cat", c); go(listHash(n)); return; }
    if ((el = t.closest("[data-apply]"))) { go(listHash(readFilters(q))); return; }
    if ((el = t.closest("[data-page]"))) { var p = readFilters(q); p.set("page", el.getAttribute("data-page")); go(listHash(p)); root.scrollIntoView({behavior: "smooth"}); return; }
    if ((el = t.closest("[data-wishlist]"))) { var w = new URLSearchParams(); w.set("ids", wish.join(",")); go(listHash(w)); return; }
    if ((el = t.closest("[data-go]"))) { go("#bp-product/" + el.getAttribute("data-go")); return; }
    if ((el = t.closest("[data-pic]"))) { root.querySelector("[data-main]").src = el.getAttribute("data-pic"); [].forEach.call(el.parentNode.children, function (b) { b.classList.toggle("on", b === el); }); }
  }

  function onChange(e) {
    var t = e.target;
    if (t.matches("[data-f], [data-stock]")) go(listHash(readFilters(state.q)));
    else if (t.matches("[data-sort]")) { var q = readFilters(state.q); if (t.value) q.set("sort", t.value); else q.delete("sort"); go(listHash(q)); }
  }

  function onSubmit(e) {
    var f = e.target.closest("[data-review]");
    if (!f) return;
    e.preventDefault();
    var body = {name: f.name.value, rating: f.rating.value, text: f.text.value, company_website: f.company_website.value};
    fetch(C.review.replace("{id}", f.getAttribute("data-review")), {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})
      .then(function () { f.outerHTML = "<p>✓ " + esc(T.review_thanks) + "</p>"; });
  }

  function start() {
    root = document.querySelector(".bookpilot-shop");
    if (!root) return;
    if (!document.getElementById("bps-style")) { var st = document.createElement("style"); st.id = "bps-style"; st.textContent = CSS; document.head.appendChild(st); }
    root.classList.add("bps");
    root.style.setProperty("--c", root.getAttribute("data-color") || C.color);
    if (C.rtl) root.setAttribute("dir", "rtl");
    opts = {category: root.getAttribute("data-category") || ""};
    if (!document.querySelector('script[src^="' + C.order_js.split("?")[0] + '"]')) {
      var s = document.createElement("script"); s.src = C.order_js; s.defer = true; document.body.appendChild(s);
    }
    root.addEventListener("click", onClick);
    root.addEventListener("change", onChange);
    root.addEventListener("submit", onSubmit);
    root.addEventListener("keydown", function (e) { if (e.key === "Enter" && e.target.matches("[data-q], [data-min], [data-max]")) { e.preventDefault(); go(listHash(readFilters(state.q))); } });
    window.addEventListener("hashchange", route);
    route();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
