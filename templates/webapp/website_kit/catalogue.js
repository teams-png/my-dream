/* BookPilot catalogue list — menu / services / products / rooms / courses / jobs, always up to date.
   <div class="bookpilot-catalogue"></div> + this script. Optional: data-category="…", data-limit="12", data-color="#…" */
(function () {
  "use strict";
  var CFG = {{ cfg|safe }};
  var CSS = ".bpc{--c:#0f766e;font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#0f172a}.bpc *{box-sizing:border-box}" +
    ".bpc .cat{font-size:19px;font-weight:700;margin:18px 0 10px}.bpc .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}" +
    ".bpc .it{background:#fff;border:1px solid #e2e8f0;border-radius:14px;overflow:hidden;display:flex;flex-direction:column}" +
    ".bpc .it img{width:100%;height:150px;object-fit:cover}.bpc .b{padding:12px 14px;display:flex;flex-direction:column;gap:4px;flex:1}" +
    ".bpc .n{font-weight:700}.bpc .d{color:#64748b;font-size:13.5px}.bpc .p{margin-top:auto;font-weight:800;color:var(--c)}.bpc .p small{color:#64748b;font-weight:500}";
  var UNIT = {hour: "/ hour", day: "/ day", night: "/ night", month: "/ month", monthly: "/ month", once: "", event: ""};
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function render(box, data) {
    box.classList.add("bpc"); box.style.setProperty("--c", box.getAttribute("data-color") || CFG.color);
    var want = (box.getAttribute("data-category") || "").toLowerCase(), limit = parseInt(box.getAttribute("data-limit") || "0", 10);
    var items = (data.items || []).filter(function (i) { return !want || (i.category || "").toLowerCase() === want; });
    if (limit) items = items.slice(0, limit);
    var groups = {}, order = [];
    items.forEach(function (i) { var k = i.category || ""; if (!groups[k]) { groups[k] = []; order.push(k); } groups[k].push(i); });
    box.innerHTML = order.map(function (k) {
      return (k && order.length > 1 ? '<div class="cat">' + esc(k) + "</div>" : "") + '<div class="grid">' + groups[k].map(function (i) {
        var sub = [i.location, i.minutes ? i.minutes + " min" : "", i.capacity ? "👤 " + i.capacity : "", i.teacher].filter(Boolean).join(" · ");
        return '<div class="it">' + (i.image ? '<img loading="lazy" src="' + esc(i.image) + '" alt="">' : "") + '<div class="b"><span class="n">' + esc(i.name) + "</span>" +
          (sub ? '<span class="d">' + esc(sub) + "</span>" : "") + (i.description ? '<span class="d">' + esc(i.description) + "</span>" : "") +
          (i.price ? '<span class="p">' + esc(data.currency) + " " + esc(i.price) + " <small>" + esc(UNIT[i.unit] || "") + "</small></span>" : "") + "</div></div>";
      }).join("") + "</div>";
    }).join("") || "<p>—</p>";
  }
  function start() {
    if (!document.getElementById("bpc-style")) { var st = document.createElement("style"); st.id = "bpc-style"; st.textContent = CSS; document.head.appendChild(st); }
    var boxes = document.querySelectorAll(".bookpilot-catalogue");
    if (!boxes.length) return;
    fetch(CFG.feed).then(function (r) { return r.json(); }).then(function (data) { boxes.forEach(function (b) { render(b, data); }); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
