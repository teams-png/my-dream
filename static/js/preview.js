/* Preview panel: a link with data-preview-url opens the record on the right (a sheet from the bottom on phones)
   instead of a new page. Ctrl/⌘-click or middle-click still opens the link itself. Esc or ✕ closes. */
(function () {
  var panel, body, last;
  function build() {
    panel = document.createElement("aside");
    panel.className = "pv";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "false");
    panel.hidden = true;
    var x = document.createElement("button");
    x.type = "button"; x.className = "pv-x msg-x"; x.textContent = "×";
    var cfg = document.getElementById("bpPalette");
    x.setAttribute("aria-label", cfg ? cfg.dataset.close : "Close");
    x.addEventListener("click", close);
    body = document.createElement("div");
    body.className = "pv-body";
    panel.appendChild(x); panel.appendChild(body);
    document.body.appendChild(panel);
  }
  function close() {
    if (!panel) return;
    panel.hidden = true;
    document.querySelectorAll(".pv-on").forEach(function (r) { r.classList.remove("pv-on"); });
    if (last) last.focus();
  }
  function open(link) {
    if (!panel) build();
    last = link;
    document.querySelectorAll(".pv-on").forEach(function (r) { r.classList.remove("pv-on"); });
    var row = link.closest(".hr-row, tr");
    if (row) row.classList.add("pv-on");
    panel.hidden = false;
    panel.classList.add("loading");
    fetch(link.dataset.previewUrl, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw r; return r.text(); })
      .then(function (html) { body.innerHTML = html; panel.classList.remove("loading"); var f = body.querySelector("a,button"); if (f) f.focus(); })
      .catch(function () { panel.hidden = true; window.location.href = link.href; });
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[data-preview-url]");
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    open(a);
  }, true);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && panel && !panel.hidden) close(); });
})();
