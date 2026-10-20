/* Keyboard shortcuts, a thin loading bar while the next page opens, and success messages that close by themselves.
   Shortcuts never fire while typing in a box: N new bill, / search, G then O overview, ? the list of shortcuts. */
(function () {
  var cfg = document.getElementById("bpPalette");
  var t = cfg ? cfg.dataset : {};

  function typing(e) {
    var el = e.target;
    return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  }

  // --- loading bar ---------------------------------------------------------
  var bar = document.createElement("div");
  bar.className = "bp-load";
  bar.setAttribute("aria-hidden", "true");
  document.body.appendChild(bar);
  function loading() { bar.classList.remove("go"); void bar.offsetWidth; bar.classList.add("go"); }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var href = a.getAttribute("href");
    if (!href || href.charAt(0) === "#" || a.target === "_blank" || a.hasAttribute("download") || a.origin !== location.origin) return;
    loading();
  });
  document.addEventListener("submit", function (e) { if (!e.defaultPrevented && !e.target.target) loading(); });
  window.addEventListener("pageshow", function () { bar.classList.remove("go"); });

  // --- messages: a close button; success messages fade after a few seconds ----
  document.querySelectorAll(".messages li").forEach(function (li) {
    var x = document.createElement("button");
    x.type = "button";
    x.className = "msg-x";
    x.setAttribute("aria-label", t.close || "Close");
    x.textContent = "×";
    x.addEventListener("click", function () { li.remove(); });
    li.appendChild(x);
    if (li.classList.contains("success") || li.classList.contains("info")) {
      setTimeout(function () { li.classList.add("bye"); setTimeout(function () { li.remove(); }, 400); }, 6000);
    }
  });

  // --- shortcuts -----------------------------------------------------------
  var help, lastG = 0;
  function showHelp() {
    if (!help) {
      help = document.createElement("div");
      help.className = "bp-pal";
      help.setAttribute("role", "dialog");
      help.setAttribute("aria-modal", "true");
      var card = document.createElement("div");
      card.className = "bp-pal-card bp-keys";
      var h = document.createElement("b"); h.textContent = t.keysTitle || "Keyboard shortcuts"; card.appendChild(h);
      [["Ctrl K", t.keySearch], ["/", t.keySearch], ["N", t.keyNew], ["G  O", t.keyHome], ["?", t.keyHelp], ["Esc", t.keyClose]]
        .forEach(function (row) {
          var d = document.createElement("div"), k = document.createElement("kbd"), s = document.createElement("span");
          k.textContent = row[0]; s.textContent = row[1] || ""; d.appendChild(k); d.appendChild(s); card.appendChild(d);
        });
      help.appendChild(card);
      help.addEventListener("mousedown", function (e) { if (e.target === help) help.hidden = true; });
      document.body.appendChild(help);
    }
    help.hidden = false;
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && help && !help.hidden) { help.hidden = true; return; }
    if (typing(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.documentElement.classList.contains("bp-pal-open")) return;
    var k = e.key;
    if (k === "/" && window.bpPalette) { e.preventDefault(); window.bpPalette.open(); }
    else if (k === "?") { e.preventDefault(); showHelp(); }
    else if (k === "n" || k === "N") {
      var newBtn = document.querySelector("[data-shortcut-new]") || document.querySelector(".sidebar .nav-bill");
      if (newBtn) { e.preventDefault(); loading(); window.location.href = newBtn.href; }
    } else if (k === "g" || k === "G") { lastG = Date.now(); }
    else if ((k === "o" || k === "O") && Date.now() - lastG < 1200 && t.home) { loading(); window.location.href = t.home; }
  });
})();
