/* Keeps the offline POS ready on this device and offers it when the internet drops. */
(function () {
  "use strict";
  const PAGE = "/restaurant/offline/", DATA = "/restaurant/offline/bootstrap.json", CACHE = "bp-offline-pos-v1";
  function warm() {
    if (!("caches" in window) || !navigator.onLine) return;
    caches.open(CACHE).then(async c => {
      c.add(DATA).then(() => c.match(DATA)).then(r => r && r.json()).then(data => {
        (data && data.items || []).filter(i => i.image).forEach(i => c.match(i.image).then(hit => hit || c.add(i.image).catch(() => {})));
      }).catch(() => {});
      const r = await fetch(PAGE, { credentials: "same-origin" });
      if (!r.ok || r.redirected) return;
      const html = await r.clone().text();
      await c.put(PAGE, r);
      // the page's own scripts, styles and fonts must be saved too
      const assets = [...new Set([...html.matchAll(/(?:src|href)="(\/static\/[^"]+)"/g)].map(m => m[1]))];
      await Promise.all(assets.map(a => c.match(a).then(hit => hit || c.add(a).catch(() => {}))));
    }).catch(() => {});
  }
  function banner(show) {
    let el = document.getElementById("netLost");
    if (!show) { if (el) el.remove(); return; }
    if (el) return;
    el = document.createElement("div");
    el.id = "netLost";
    el.setAttribute("role", "alert");
    el.style.cssText = "position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:200;display:flex;gap:12px;align-items:center;padding:12px 16px;border-radius:16px;background:#b42318;color:#fff;font-weight:700;box-shadow:0 16px 40px rgba(0,0,0,.3);max-width:92vw";
    el.innerHTML = '<span>📴 ' + (document.documentElement.dataset.offlineMsg || "No internet connection") + '</span><a href="' + PAGE + '" style="background:#fff;color:#b42318;padding:8px 12px;border-radius:10px;white-space:nowrap">' + (document.documentElement.dataset.offlineCta || "Open offline POS →") + "</a>";
    document.body.appendChild(el);
  }
  addEventListener("offline", () => banner(true));
  addEventListener("online", () => { banner(false); warm(); });
  if (!navigator.onLine) banner(true);
  if ("requestIdleCallback" in window) requestIdleCallback(warm); else setTimeout(warm, 2000);
})();
