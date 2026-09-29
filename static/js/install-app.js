/* Shows an "Install app" button where the browser supports installing the
 * site as an app (Chrome, Edge, Android), and short instructions on iPhone /
 * iPad. Hidden inside the installed app and the BookPilot desktop/mobile apps. */
(function () {
  "use strict";
  const buttons = [...document.querySelectorAll("[data-install-app]")];
  if (!buttons.length) return;
  const installed = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true ||
    /BookPilotApp/.test(navigator.userAgent);
  if (installed) return;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  let deferred = null;
  const show = on => buttons.forEach(b => { b.hidden = !on; });

  addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferred = e; show(true); });
  addEventListener("appinstalled", () => { deferred = null; show(false); });
  if (ios) show(true);

  function iosHelp() {
    const t = document.documentElement.dataset;
    const box = document.createElement("div");
    box.setAttribute("role", "dialog");
    box.style.cssText = "position:fixed;left:12px;right:12px;bottom:18px;z-index:300;background:#12162b;color:#fff;border-radius:18px;padding:16px 18px;box-shadow:0 20px 50px rgba(0,0,0,.35);font:15px/1.45 system-ui,sans-serif";
    box.innerHTML = `<b style="display:block;font-size:16px;margin-bottom:4px">${t.installTitle || "Install BookPilot"}</b>${t.installIos || "Tap the Share button, then “Add to Home Screen”."}<button type="button" style="position:absolute;top:8px;right:10px;border:0;background:none;color:#fff;font-size:20px;cursor:pointer" aria-label="Close">×</button>`;
    box.querySelector("button").onclick = () => box.remove();
    document.body.appendChild(box);
  }

  buttons.forEach(b => b.addEventListener("click", async () => {
    if (deferred) {
      deferred.prompt();
      const choice = await deferred.userChoice.catch(() => null);
      if (choice && choice.outcome === "accepted") show(false);
      deferred = null;
    } else if (ios) {
      iosHelp();
    }
  }));
})();
