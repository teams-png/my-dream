/* A short guided tour: a bubble points at one thing at a time and moves on when the person does it.
 * Usage: BpTour.start([{el: "#id or .selector", text: "…", next: true}], {done: "Finish", skip: "Skip", onEnd})
 * A step without `next` waits for a click on its element. Steps whose element is missing are skipped.
 */
(function () {
  "use strict";
  const css = `
  .bp-tour-bubble{position:fixed;inset:auto;margin:0;border:0;overflow:visible;z-index:2147483647;max-width:300px;background:#0f1a14;color:#fff;border-radius:14px;
    padding:14px 16px 12px;font:14px/1.45 Inter,system-ui,sans-serif;box-shadow:0 18px 40px rgba(0,0,0,.3)}
  .bp-tour-bubble b{display:block;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#c6f432;margin-bottom:4px}
  .bp-tour-bubble .row{display:flex;justify-content:space-between;gap:8px;margin-top:10px}
  .bp-tour-bubble button{border:0;border-radius:9px;padding:7px 12px;font:inherit;font-weight:600;cursor:pointer}
  .bp-tour-bubble .skip{background:transparent;color:#b9c7be}
  .bp-tour-bubble .next{background:#c6f432;color:#10240f}
  .bp-tour-bubble:after{content:"";position:absolute;width:14px;height:14px;background:#0f1a14;transform:rotate(45deg);left:var(--ax,24px)}
  .bp-tour-bubble.below:after{top:-6px}.bp-tour-bubble.above:after{bottom:-6px}
  .bp-tour-glow{outline:3px solid #c6f432!important;outline-offset:3px;border-radius:12px;animation:bpTourPulse 1.4s ease-in-out infinite}
  @keyframes bpTourPulse{50%{outline-color:rgba(198,244,50,.35)}}`;

  function start(steps, opts) {
    opts = opts || {};
    if (!document.getElementById("bp-tour-css")) {
      const s = document.createElement("style"); s.id = "bp-tour-css"; s.textContent = css; document.head.appendChild(s);
    }
    let i = -1, bubble = null, target = null, waitTimer = null;

    function clear() {
      if (target) { target.classList.remove("bp-tour-glow"); target.removeEventListener("click", onTarget, true); }
      if (bubble) bubble.remove();
      bubble = target = null; clearTimeout(waitTimer);
    }
    function end(finished) {
      clear(); window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true);
      if (opts.onEnd) opts.onEnd(finished);
    }
    function onTarget() { setTimeout(go, 350); }
    function find(sel) { const el = document.querySelector(sel); return el && el.getClientRects().length ? el : null; }

    function go() {
      clear(); i += 1;
      if (i >= steps.length) return end(true);
      const step = steps[i];
      let tries = 0;
      (function wait() {  // the element may appear a moment later (a dialog opening)
        const el = find(step.el);
        if (!el) { if (++tries > 25) return go(); waitTimer = setTimeout(wait, 120); return; }
        show(el, step);
      })();
    }

    function show(el, step) {
      target = el;
      el.classList.add("bp-tour-glow");
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      bubble = document.createElement("div");
      bubble.className = "bp-tour-bubble";
      bubble.setAttribute("role", "dialog");
      bubble.innerHTML = `<b>${(opts.stepLabel || "Step")} ${i + 1}/${steps.length}</b><div></div><div class="row">
        <button type="button" class="skip">${opts.skip || "Skip tour"}</button>
        ${step.next || i === steps.length - 1 ? `<button type="button" class="next">${i === steps.length - 1 ? (opts.done || "Done") : (opts.nextLabel || "Next")}</button>` : ""}</div>`;
      bubble.children[1].textContent = step.text;
      document.body.appendChild(bubble);
      if (bubble.showPopover) {  // the top layer: stays above an open modal dialog too
        bubble.setAttribute("popover", "manual");
        try { bubble.showPopover(); } catch (e) { /* older browser: plain fixed bubble */ }
      }
      bubble.querySelector(".skip").onclick = () => end(false);
      const next = bubble.querySelector(".next");
      if (next) next.onclick = go;
      if (!step.next) el.addEventListener("click", onTarget, true);
      place();
    }

    function place() {
      if (!bubble || !target) return;
      const r = target.getBoundingClientRect(), b = bubble.getBoundingClientRect(), gap = 14;
      const below = r.bottom + gap + b.height < window.innerHeight || r.top < b.height + gap;
      const top = below ? r.bottom + gap : r.top - b.height - gap;
      const left = Math.max(8, Math.min(window.innerWidth - b.width - 8, r.left + r.width / 2 - b.width / 2));
      bubble.classList.toggle("below", below); bubble.classList.toggle("above", !below);
      bubble.style.top = Math.max(8, top) + "px"; bubble.style.left = left + "px";
      bubble.style.setProperty("--ax", Math.max(14, Math.min(b.width - 28, r.left + r.width / 2 - left - 7)) + "px");
    }
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    go();
    return { stop: () => end(false) };
  }
  window.BpTour = { start };
})();
