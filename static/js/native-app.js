/* Runs only inside the BookPilot Android / iOS app (Capacitor):
 *  - window.print() and receipt printing go through the phone's print
 *    service (the app's WebView ignores the normal print call);
 *  - the Android back button closes dialogs and goes back instead of
 *    quitting the app. */
(function () {
  "use strict";
  const C = window.Capacitor;
  if (!C || typeof C.isNativePlatform !== "function" || !C.isNativePlatform()) return;
  document.documentElement.classList.add("bp-native");
  const plugin = (name) => (C.Plugins && C.Plugins[name]) || (C.registerPlugin ? C.registerPlugin(name) : null);

  const Print = plugin("BookPilotPrint");
  if (Print) {
    const printHtml = (html, baseUrl) => Print.printHtml({ html, baseUrl: baseUrl || location.href, jobName: document.title || "BookPilot" });
    window.bookpilotNative = {
      printHtml,
      printUrl: async (url) => {
        const absolute = new URL(url, location.href).href;
        const res = await fetch(absolute, { credentials: "same-origin" });
        if (!res.ok) throw new Error("Could not load the page to print (" + res.status + ").");
        return printHtml(await res.text(), absolute);
      },
    };
    window.print = () => { printHtml("<!doctype html>" + document.documentElement.outerHTML).catch(() => {}); };
  }

  const App = plugin("App");
  if (App && App.addListener) {
    App.addListener("backButton", ({ canGoBack }) => {
      const dialog = document.querySelector("dialog[open]");
      if (dialog) { dialog.close(); return; }
      if (document.body.classList.contains("ticket-open")) { document.body.classList.remove("ticket-open"); return; }
      if (canGoBack) history.back(); else App.exitApp();
    });
  }
})();
