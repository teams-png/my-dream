/* Top bar extras. Bell: unread count and the latest notifications in a dropdown. Pins: ☆ beside a page title
   pins that page to the top of the menu (kept in this browser, per business). */
(function () {
  var cfg = document.getElementById("bpPalette");
  if (!cfg) return;
  var t = cfg.dataset;

  // --- bell ----------------------------------------------------------------
  var bell = document.querySelector("[data-bell]"), drop = null;
  function load(render) {
    return fetch(t.feed, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d) return;
      var n = bell.querySelector("[data-bell-n]");
      n.hidden = !d.unread; n.textContent = d.unread > 9 ? "9+" : d.unread;
      if (render) render(d);
    }).catch(function () {});
  }
  function show(d) {
    if (!drop) {
      drop = document.createElement("div");
      drop.className = "bell-drop";
      drop.setAttribute("role", "dialog");
      document.body.appendChild(drop);
      document.addEventListener("click", function (e) { if (drop && !drop.hidden && !drop.contains(e.target) && !bell.contains(e.target)) drop.hidden = true; });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape" && drop) drop.hidden = true; });
    }
    drop.innerHTML = "";
    var h = document.createElement("b"); h.textContent = t.bellTitle; drop.appendChild(h);
    if (!d.items.length) { var p = document.createElement("p"); p.className = "bell-empty"; p.textContent = t.bellEmpty; drop.appendChild(p); }
    d.items.forEach(function (it) {
      var a = document.createElement("a"); a.href = t.bellAll; a.className = it.read ? "" : "unread";
      var b = document.createElement("strong"); b.textContent = it.title; a.appendChild(b);
      if (it.message) { var m = document.createElement("span"); m.textContent = it.message; a.appendChild(m); }
      var w = document.createElement("small"); w.textContent = it.when; a.appendChild(w);
      drop.appendChild(a);
    });
    var all = document.createElement("a"); all.href = t.bellAll; all.className = "bell-all"; all.textContent = t.bellSeeAll + " →";
    drop.appendChild(all);
    var r = bell.getBoundingClientRect();
    drop.style.top = (r.bottom + window.scrollY + 8) + "px";
    drop.style.insetInlineEnd = Math.max(12, document.documentElement.clientWidth - r.right) + "px";
    drop.hidden = false;
  }
  if (bell && t.feed) {
    load();
    bell.addEventListener("click", function () { if (drop && !drop.hidden) { drop.hidden = true; return; } load(show); });
  }

  // --- pins ----------------------------------------------------------------
  var key = "bp.pins." + (t.company || ""), pinBtn = document.querySelector("[data-pin]"), box = document.getElementById("bpPins");
  function read() { try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch (e) { return []; } }
  function write(list) { try { localStorage.setItem(key, JSON.stringify(list.slice(0, 8))); } catch (e) {} }
  var here = location.pathname + location.search;
  function paint() {
    var list = read();
    if (box) {
      box.innerHTML = "";
      if (list.length) {
        var h = document.createElement("div"); h.className = "pins-h"; h.textContent = "★ " + t.pinned; box.appendChild(h);
        list.forEach(function (p) {
          var a = document.createElement("a"); a.className = "nav-link" + (p.href === here ? " active" : ""); a.href = p.href;
          var s = document.createElement("span"); s.textContent = p.label; a.appendChild(s); box.appendChild(a);
        });
      }
    }
    if (pinBtn) {
      var on = list.some(function (p) { return p.href === here; });
      pinBtn.textContent = on ? "★" : "☆";
      pinBtn.setAttribute("aria-pressed", on ? "true" : "false");
      pinBtn.title = on ? t.unpinLabel : t.pinLabel;
      pinBtn.setAttribute("aria-label", pinBtn.title);
    }
  }
  if (pinBtn) {
    pinBtn.addEventListener("click", function () {
      var list = read(), i = list.findIndex(function (p) { return p.href === here; });
      if (i >= 0) list.splice(i, 1);
      else { var h1 = document.querySelector(".topbar h1"); list.unshift({ href: here, label: (h1 ? h1.textContent : document.title).trim().slice(0, 40) }); }
      write(list); paint();
    });
  }
  paint();
})();
