/* Ctrl+K / ⌘K search: menu pages (read from the sidebar, so only pages this member may open) plus the business's
   customers, invoices, products, staff… from the server. Arrow keys move, Enter opens, Esc closes. */
(function () {
  var cfg = document.getElementById("bpPalette");
  if (!cfg) return;
  var url = cfg.dataset.url, t = cfg.dataset;
  var box, input, list, items = [], active = 0, timer = null, seq = 0;

  function pages() {
    var seen = {}, out = [];
    document.querySelectorAll(".sidebar a.nav-link[href]").forEach(function (a) {
      var href = a.getAttribute("href"), label = (a.textContent || "").replace(/\s+/g, " ").trim();
      if (!label || !href || href.charAt(0) !== "/" || seen[href] || /logout/.test(href)) return;
      seen[href] = 1;
      var sec = a.closest("details"), group = sec ? sec.querySelector("summary").textContent.trim() : "";
      out.push({ group: t.pages, title: label, sub: group, url: href });
    });
    return out;
  }

  function build() {
    box = document.createElement("div");
    box.className = "bp-pal";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", t.title);
    box.innerHTML = '<div class="bp-pal-card"><div class="bp-pal-in"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input type="text" autocomplete="off" spellcheck="false"><kbd>Esc</kbd></div><div class="bp-pal-list" role="listbox"></div><div class="bp-pal-foot"></div></div>';
    document.body.appendChild(box);
    input = box.querySelector("input");
    list = box.querySelector(".bp-pal-list");
    input.placeholder = t.placeholder;
    input.setAttribute("aria-label", t.placeholder);
    box.querySelector(".bp-pal-foot").textContent = t.foot;
    box.addEventListener("mousedown", function (e) { if (e.target === box) close(); });
    input.addEventListener("input", search);
    input.addEventListener("keydown", keys);
  }

  function render(rows) {
    items = rows;
    active = 0;
    list.innerHTML = "";
    if (!rows.length) {
      var empty = document.createElement("div");
      empty.className = "bp-pal-empty";
      empty.textContent = input.value.trim() ? t.empty : t.hint;
      list.appendChild(empty);
      return;
    }
    var last = null;
    rows.forEach(function (r, i) {
      if (r.group !== last) {
        var g = document.createElement("div");
        g.className = "bp-pal-group";
        g.textContent = r.group;
        list.appendChild(g);
        last = r.group;
      }
      var a = document.createElement("a");
      a.href = r.url;
      a.className = "bp-pal-item";
      a.setAttribute("role", "option");
      a.dataset.i = i;
      var b = document.createElement("b"); b.textContent = r.title; a.appendChild(b);
      if (r.sub) { var s = document.createElement("small"); s.textContent = r.sub; a.appendChild(s); }
      a.addEventListener("mousemove", function () { mark(i); });
      list.appendChild(a);
    });
    mark(0);
  }

  function mark(i) {
    active = i;
    list.querySelectorAll(".bp-pal-item").forEach(function (a) {
      var on = +a.dataset.i === i;
      a.classList.toggle("on", on);
      a.setAttribute("aria-selected", on ? "true" : "false");
      if (on) a.scrollIntoView({ block: "nearest" });
    });
  }

  function search() {
    var q = input.value.trim().toLowerCase();
    var local = pages().filter(function (p) { return !q || p.title.toLowerCase().indexOf(q) >= 0 || p.sub.toLowerCase().indexOf(q) >= 0; });
    render(q ? local.slice(0, 8) : local.slice(0, 10));
    clearTimeout(timer);
    if (q.length < 2) return;
    var mine = ++seq;
    timer = setTimeout(function () {
      fetch(url + "?q=" + encodeURIComponent(q), { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : { results: [] }; })
        .then(function (d) { if (mine === seq) render(local.slice(0, 6).concat(d.results || [])); })
        .catch(function () {});
    }, 180);
  }

  function keys(e) {
    if (e.key === "ArrowDown") { e.preventDefault(); if (items.length) mark((active + 1) % items.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (items.length) mark((active - 1 + items.length) % items.length); }
    else if (e.key === "Enter") { e.preventDefault(); if (items[active]) window.location.href = items[active].url; }
    else if (e.key === "Escape") { close(); }
  }

  function open() {
    if (!box) build();
    box.hidden = false;
    document.documentElement.classList.add("bp-pal-open");
    input.value = "";
    search();
    setTimeout(function () { input.focus(); }, 0);
  }
  function close() {
    if (!box) return;
    box.hidden = true;
    document.documentElement.classList.remove("bp-pal-open");
  }
  window.bpPalette = { open: open, close: close };

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); box && !box.hidden ? close() : open(); }
  });
  document.querySelectorAll("[data-palette-open]").forEach(function (b) { b.addEventListener("click", open); });
})();
