/* List tools. Inline edit: a cell with data-inline-url / data-field turns into a box on click; Enter or leaving it
   saves, Esc cancels. Bulk: tick rows (.bulk-check) and the bar of a [data-bulk-form] appears with how many are
   ticked; its ids go with the form. */
(function () {
  var tokenEl = document.querySelector("[name=csrfmiddlewaretoken]");
  var token = tokenEl ? tokenEl.value : "";

  document.querySelectorAll("[data-inline-url]").forEach(function (cell) {
    cell.classList.add("inline-edit");
    cell.tabIndex = 0;
    cell.title = cell.dataset.hint || "";
    function edit() {
      if (cell.querySelector("input")) return;
      var old = cell.textContent.trim(), box = document.createElement("input");
      box.type = "text"; box.inputMode = "decimal"; box.value = old; box.className = "inline-box";
      box.setAttribute("aria-label", cell.dataset.label || "");
      cell.textContent = ""; cell.appendChild(box); box.focus(); box.select();
      var done = false;
      function finish(save) {
        if (done) return; done = true;
        var value = box.value.trim();
        if (!save || value === old) { cell.textContent = old; return; }
        cell.textContent = value; cell.classList.add("saving");
        var body = new FormData(); body.append("field", cell.dataset.field); body.append("value", value);
        fetch(cell.dataset.inlineUrl, { method: "POST", body: body, credentials: "same-origin", headers: { "X-CSRFToken": token } })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok && d.ok, d: d }; }); })
          .then(function (res) {
            cell.classList.remove("saving");
            if (res.ok) { cell.textContent = res.d.value; cell.classList.add("saved"); setTimeout(function () { cell.classList.remove("saved"); }, 1200); }
            else { cell.textContent = old; cell.classList.add("bad"); cell.title = res.d.error || ""; setTimeout(function () { cell.classList.remove("bad"); }, 2000); }
          })
          .catch(function () { cell.classList.remove("saving"); cell.textContent = old; });
      }
      box.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); finish(true); }
        else if (e.key === "Escape") { e.preventDefault(); finish(false); }
      });
      box.addEventListener("blur", function () { finish(true); });
    }
    cell.addEventListener("click", edit);
    cell.addEventListener("keydown", function (e) { if (e.key === "Enter" && !cell.querySelector("input")) { e.preventDefault(); edit(); } });
  });

  document.querySelectorAll("[data-bulk-form]").forEach(function (form) {
    var checks = function () { return Array.prototype.slice.call(document.querySelectorAll(".bulk-check")); };
    var all = document.querySelector(".bulk-all"), count = form.querySelector("[data-bulk-count]");
    function update() {
      var on = checks().filter(function (c) { return c.checked; });
      form.hidden = !on.length;
      if (count) count.textContent = on.length;
      form.querySelectorAll("input[name=ids]").forEach(function (i) { i.remove(); });
      on.forEach(function (c) { var h = document.createElement("input"); h.type = "hidden"; h.name = "ids"; h.value = c.value; form.appendChild(h); });
      if (all) all.checked = on.length && on.length === checks().length;
    }
    document.addEventListener("change", function (e) {
      if (e.target === all) checks().forEach(function (c) { c.checked = all.checked; });
      if (e.target === all || e.target.classList.contains("bulk-check")) update();
    });
    var action = form.querySelector("select[name=action]");
    function show() {
      form.querySelectorAll("[data-for-action]").forEach(function (el) { el.hidden = !action || el.dataset.forAction !== action.value; });
    }
    if (action) action.addEventListener("change", show);
    show(); update();
  });
})();
