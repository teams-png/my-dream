/* Quick add: a "+ New" button beside every customer / supplier dropdown in a form opens the add form in a popup;
   once saved, the new record is added to the dropdown and chosen — the half-filled form is never left. */
(function () {
  var cfg = document.getElementById("bpPalette");
  var inPopup = document.documentElement.classList.contains("bp-popup");
  if (inPopup) {
    // inside the popup: Cancel closes it instead of leaving for the list page
    document.querySelectorAll("form a.btn-secondary").forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        window.parent.postMessage({ type: "bp-quick-cancel" }, window.location.origin);
      });
    });
    return;
  }
  if (!cfg) return;
  var t = cfg.dataset, kinds = { customer: t.addCustomer, supplier: t.addSupplier };
  var modal, frame, target = null;

  function build() {
    modal = document.createElement("div");
    modal.className = "bp-pal bp-qa";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    var card = document.createElement("div");
    card.className = "bp-pal-card";
    var head = document.createElement("div");
    head.className = "bp-qa-head";
    var title = document.createElement("b");
    var x = document.createElement("button");
    x.type = "button"; x.className = "msg-x"; x.textContent = "×"; x.setAttribute("aria-label", t.close || "Close");
    x.addEventListener("click", close);
    head.appendChild(title); head.appendChild(x);
    frame = document.createElement("iframe");
    frame.className = "bp-qa-frame";
    card.appendChild(head); card.appendChild(frame);
    modal.appendChild(card);
    modal.addEventListener("mousedown", function (e) { if (e.target === modal) close(); });
    document.body.appendChild(modal);
    modal._title = title;
  }
  function open(select, kind) {
    if (!modal) build();
    target = { select: select, kind: kind };
    modal._title.textContent = (kind === "supplier" ? t.newSupplier : t.newCustomer) || t.addTitle;
    frame.src = kinds[kind] + "?popup=1";
    modal.hidden = false;
    document.documentElement.classList.add("bp-pal-open");
  }
  function close() {
    if (!modal) return;
    modal.hidden = true;
    frame.src = "about:blank";
    document.documentElement.classList.remove("bp-pal-open");
  }
  window.addEventListener("message", function (e) {
    if (e.origin !== window.location.origin || !e.data) return;
    if (e.data.type === "bp-quick-cancel") { close(); return; }
    if (e.data.type !== "bp-quick-added" || !target || e.data.kind !== target.kind) return;
    var opt = new Option(e.data.name, e.data.id, true, true);
    target.select.appendChild(opt);
    target.select.value = String(e.data.id);
    target.select.dispatchEvent(new Event("change", { bubbles: true }));
    close();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && modal && !modal.hidden) close(); });

  Object.keys(kinds).forEach(function (kind) {
    if (!kinds[kind]) return;
    document.querySelectorAll('form select[name="' + kind + '"]').forEach(function (select) {
      var form = select.form;
      if (!form || (form.getAttribute("method") || "get").toLowerCase() !== "post" || select.dataset.noQuickAdd !== undefined) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "btn btn-secondary bp-qa-btn";
      b.textContent = "+ " + t.addNew;
      b.title = t.addTitle;
      b.addEventListener("click", function () { open(select, kind); });
      var wrap = document.createElement("div");
      wrap.className = "bp-qa-wrap";
      select.parentNode.insertBefore(wrap, select);
      wrap.appendChild(select);
      wrap.appendChild(b);
    });
  });
})();
